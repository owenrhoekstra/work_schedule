from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from schedule.models import CompanyMembership
from schedule.tests._helpers import login_as
from schedule.tests.factories import make_company

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


def _make_user(username, **kwargs):
    return User.objects.create_user(username=username, password="pw-not-used", **kwargs)


def _make_membership(user, company, role="member", status="active"):
    return CompanyMembership.objects.create(
        user=user, company=company, role=role, status=status
    )


@override_settings(CACHES=_LOCMEM_CACHES)
class CompanyPickerTests(TestCase):
    def setUp(self):
        self.user = _make_user("picker")
        self.client.force_login(self.user)

    def test_zero_memberships_redirects_to_waiting(self):
        resp = self.client.get(reverse("company_picker"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("waiting"))

    def test_one_membership_auto_selects_and_redirects_home(self):
        company = make_company()
        _make_membership(self.user, company)
        resp = self.client.get(reverse("company_picker"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("home"))
        self.assertEqual(self.client.session["company_id"], str(company.id))

    def test_multiple_memberships_renders_picker(self):
        a = make_company(name="Alpha")
        b = make_company(name="Beta")
        _make_membership(self.user, a)
        _make_membership(self.user, b)
        resp = self.client.get(reverse("company_picker"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Alpha")
        self.assertContains(resp, "Beta")

    def test_posting_valid_company_sets_session_and_redirects(self):
        a = make_company(name="Alpha")
        b = make_company(name="Beta")
        _make_membership(self.user, a)
        _make_membership(self.user, b)
        resp = self.client.post(reverse("company_picker"), {"company_id": str(b.id)})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("home"))
        self.assertEqual(self.client.session["company_id"], str(b.id))

    def test_posting_unknown_company_rerenders_with_error(self):
        a = make_company(name="Alpha")
        b = make_company(name="Beta")
        _make_membership(self.user, a)
        _make_membership(self.user, b)
        resp = self.client.post(
            reverse("company_picker"),
            {"company_id": "00000000-0000-0000-0000-000000000000"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Please choose a company")

    def test_pending_membership_not_listed(self):
        a = make_company(name="Alpha")
        _make_membership(self.user, a, status="pending")
        resp = self.client.get(reverse("company_picker"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("waiting"))

    def test_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("company_picker"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("login"), resp.url)


@override_settings(CACHES=_LOCMEM_CACHES)
class WaitingViewTests(TestCase):
    def setUp(self):
        self.user = _make_user("waiter")
        self.client.force_login(self.user)

    def test_renders(self):
        resp = self.client.get(reverse("waiting"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Waiting for approval")

    def test_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("waiting"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("login"), resp.url)


@override_settings(CACHES=_LOCMEM_CACHES, TENANT_ENFORCEMENT=True)
class TenantEnforcementTests(TestCase):
    def test_tenanted_path_without_company_redirects_to_picker(self):
        user = _make_user("enforced")
        self.client.force_login(user)
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("company_picker"))

    def test_tenanted_path_with_session_company_passes(self):
        from schedule.models import CompanyMembership

        user = _make_user("enforced2")
        company = make_company()
        CompanyMembership.objects.create(
            user=user, company=company, role="member", status="active"
        )
        login_as(self.client, user, company)
        resp = self.client.get(reverse("home"))
        # home requires schedule.view_shift which this user lacks.
        # What matters: not redirected to picker (has a viable company).
        self.assertEqual(resp.status_code, 403)

    def test_exempt_path_no_company_passes(self):
        user = _make_user("enforced3")
        self.client.force_login(user)
        resp = self.client.get(reverse("profile"))
        self.assertEqual(resp.status_code, 200)

    def test_platform_admin_uses_default_company(self):
        user = _make_user("admin", is_staff=True)
        make_company()
        self.client.force_login(user)
        resp = self.client.get(reverse("home"))
        self.assertNotEqual(resp.status_code, 302)


@override_settings(CACHES=_LOCMEM_CACHES)
class LoginAsHelperTests(TestCase):
    def test_sets_session_company(self):
        user = _make_user("las")
        company = make_company()
        login_as(self.client, user, company)
        self.assertEqual(self.client.session["company_id"], str(company.id))

    def test_accepts_pk_string(self):
        user = _make_user("las2")
        company = make_company()
        login_as(self.client, user, str(company.id))
        self.assertEqual(self.client.session["company_id"], str(company.id))

    def test_accepts_no_company(self):
        user = _make_user("las3")
        login_as(self.client, user)
        self.assertNotIn("company_id", self.client.session)
