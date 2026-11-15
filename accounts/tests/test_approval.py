from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse

from schedule.models import CompanyMembership

from .factories import (
    make_company,
    make_employee,
    make_superuser,
)

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


def _pending_membership(user, company, role="member"):
    return CompanyMembership.objects.create(
        user=user, company=company, role=role, status="pending"
    )


def _active_membership(user, company, role="member"):
    return CompanyMembership.objects.create(
        user=user, company=company, role=role, status="active"
    )


@override_settings(CACHES=_LOCMEM_CACHES)
class PendingAccountsViewTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.admin = make_superuser("boss", company=self.company)
        self.client.force_login(self.admin)
        session = self.client.session
        session["company_id"] = str(self.company.id)
        session.save()

    def test_lists_pending_memberships_for_current_company(self):
        user = User.objects.create_user(
            username="pending", password="p", email="p@x.com", is_active=False
        )
        _pending_membership(user, self.company)
        resp = self.client.get(reverse("pending_accounts"))
        self.assertEqual(len(resp.context["pending"]), 1)
        self.assertEqual(resp.context["pending"][0].user, user)

    def test_active_users_do_not_appear(self):
        user = User.objects.create_user(
            username="active", password="p", email="a@x.com", is_active=True
        )
        _active_membership(user, self.company)
        resp = self.client.get(reverse("pending_accounts"))
        self.assertEqual(list(resp.context["pending"]), [])

    def test_other_company_pending_memberships_excluded(self):
        other_company = make_company(name="Other")
        user = User.objects.create_user(
            username="otherco", password="p", email="o@x.com", is_active=False
        )
        _pending_membership(user, other_company)
        resp = self.client.get(reverse("pending_accounts"))
        self.assertEqual(list(resp.context["pending"]), [])

    def test_oidc_user_with_pending_membership_appears(self):
        """OIDC users start is_active=True but their membership is
        pending. The queue must show them so a manager can approve the
        company access even though the account is technically active.
        """
        user = User.objects.create_user(
            username="oidcuser", password="unused", email="oidc@x.com", is_active=True
        )
        _pending_membership(user, self.company)
        resp = self.client.get(reverse("pending_accounts"))
        self.assertEqual(len(resp.context["pending"]), 1)
        self.assertEqual(resp.context["pending"][0].user, user)


@override_settings(CACHES=_LOCMEM_CACHES)
class ApproveAccountTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.admin = make_superuser("boss2", company=self.company)
        self.client.force_login(self.admin)
        session = self.client.session
        session["company_id"] = str(self.company.id)
        session.save()

        self.emp = make_employee(email="newbie@example.com", company=self.company)
        self.user = User.objects.create_user(
            username="newbie",
            password="p",
            email=self.emp.email,
            is_active=True,
        )
        self.emp.user = self.user
        self.emp.save()
        self.membership = _pending_membership(self.user, self.company)

    def test_approve_activates_membership_and_user(self):
        resp = self.client.post(reverse("approve_account", args=[self.user.pk]))
        self.assertEqual(resp.status_code, 302)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.status, "active")
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertTrue(self.user.groups.filter(name="Staff").exists())

    @patch("schedule.notifications.send_account_approved_email")
    def test_approve_with_notify_sends_email(self, mock_send):
        mock_send.return_value = (True, None)
        self.client.post(
            reverse("approve_account", args=[self.user.pk]),
            {"notify": "1"},
        )
        mock_send.assert_called_once()

    @patch("schedule.notifications.send_account_approved_email")
    def test_approve_without_notify_skips_email(self, mock_send):
        self.client.post(reverse("approve_account", args=[self.user.pk]))
        mock_send.assert_not_called()

    def test_approve_get_redirects_no_action(self):
        """GET doesn't mutate — the membership stays pending.

        User.is_active is no longer a useful signal here: under the
        multi-tenancy contract the account is active from signup and
        CompanyMembership.status is the access gate. Assert the
        membership status, not the account flag.
        """
        self.client.get(reverse("approve_account", args=[self.user.pk]))
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.status, "pending")

    def test_approve_without_pending_membership_at_company_errors(self):
        """Approving a user who has no pending membership at the current
        company (e.g., they're pending at a different company) is
        rejected. Cross-company approval must not leak access.
        """
        other = make_company(name="Other")
        stranger = User.objects.create_user(
            username="stranger", password="p", email="s@x.com", is_active=False
        )
        _pending_membership(stranger, other)

        resp = self.client.post(reverse("approve_account", args=[stranger.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(
            CompanyMembership.objects.filter(
                user=stranger, company=self.company
            ).exists()
        )
