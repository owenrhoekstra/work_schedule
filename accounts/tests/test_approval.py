from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse

from .factories import make_employee, make_staff_user, make_superuser

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


@override_settings(CACHES=_LOCMEM_CACHES)
class PendingAccountsViewTests(TestCase):
    def setUp(self):
        self.admin = make_superuser("boss")
        self.client.force_login(self.admin)

    def test_lists_inactive_users_with_active_employee(self):
        emp = make_employee(email="pending@example.com")
        pending = User.objects.create_user(
            username="pending", password="p", email=emp.email, is_active=False
        )
        emp.user = pending
        emp.save()
        resp = self.client.get(reverse("pending_accounts"))
        self.assertIn(pending, resp.context["pending"])

    def test_excludes_inactive_users_without_employee(self):
        User.objects.create_user(username="orphan", password="p", is_active=False)
        resp = self.client.get(reverse("pending_accounts"))
        self.assertEqual(list(resp.context["pending"]), [])

    def test_excludes_inactive_employee_users(self):
        emp = make_employee(email="gone@example.com")
        emp.is_active = False
        emp.last_day = emp.start_date  # past
        emp.save()
        user = User.objects.create_user(
            username="gone", password="p", email=emp.email, is_active=False
        )
        emp.user = user
        emp.save()
        resp = self.client.get(reverse("pending_accounts"))
        self.assertNotIn(user, resp.context["pending"])


@override_settings(CACHES=_LOCMEM_CACHES)
class ApproveAccountTests(TestCase):
    def setUp(self):
        self.admin = make_superuser("boss2")
        self.client.force_login(self.admin)
        emp = make_employee(email="newbie@example.com")
        self.user = User.objects.create_user(
            username="newbie", password="p", email=emp.email, is_active=False
        )
        emp.user = self.user
        emp.save()
        self.emp = emp

    def test_approve_activates_user_and_adds_to_staff_group(self):
        resp = self.client.post(
            reverse("approve_account", args=[self.user.pk]),
        )
        self.assertEqual(resp.status_code, 302)
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
        # GET on approve view should not change user state
        self.client.get(reverse("approve_account", args=[self.user.pk]))
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
