from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, Group, User
from django.test import RequestFactory, TestCase, override_settings

from accounts.context_processors import auth_flags, pending_accounts
from schedule.models import CompanyMembership

from .factories import make_company, make_employee, make_staff_user, make_superuser

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


@override_settings(CACHES=_LOCMEM_CACHES)
class PendingAccountsContextTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.company = make_company()

    def test_anonymous_returns_empty(self):
        request = self.factory.get("/")
        request.user = AnonymousUser()
        request.company = self.company
        self.assertEqual(pending_accounts(request), {})

    def test_staff_without_add_employee_permission(self):
        user = make_staff_user("plain", company=self.company)
        request = self.factory.get("/")
        request.user = user
        request.company = self.company
        self.assertEqual(pending_accounts(request), {})

    def test_manager_sees_count(self):
        admin = make_superuser(company=self.company)
        emp = make_employee(email="pend@example.com", company=self.company)
        pending_user = User.objects.create_user(
            username="pend",
            password="p",
            email=emp.email,
            is_active=False,
        )
        emp.user = pending_user
        emp.save()
        CompanyMembership.objects.create(
            user=pending_user,
            company=self.company,
            role="member",
            status="pending",
        )

        request = self.factory.get("/")
        request.user = admin
        request.company = self.company
        self.assertEqual(pending_accounts(request)["pending_accounts_count"], 1)

    def test_no_company_context_returns_empty(self):
        admin = make_superuser(company=self.company)
        request = self.factory.get("/")
        request.user = admin
        # Deliberately no request.company.
        self.assertEqual(pending_accounts(request), {})

    def test_db_error_returns_empty(self):
        admin = make_superuser(company=self.company)
        request = self.factory.get("/")
        request.user = admin
        request.company = self.company
        with patch("schedule.models.CompanyMembership.objects.filter") as mock_filter:
            mock_filter.side_effect = Exception("db down")
            self.assertEqual(pending_accounts(request), {})


@override_settings(CACHES=_LOCMEM_CACHES)
class AuthFlagsContextTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.company = make_company()

    def test_anonymous_all_false(self):
        request = self.factory.get("/")
        request.user = AnonymousUser()
        flags = auth_flags(request)
        self.assertFalse(flags["is_platform_admin"])
        self.assertFalse(flags["is_company_admin"])
        self.assertFalse(flags["is_team_admin"])

    def test_plain_user_all_false(self):
        user = make_staff_user(company=self.company)
        request = self.factory.get("/")
        request.user = user
        request.company = self.company
        flags = auth_flags(request)
        self.assertFalse(flags["is_platform_admin"])
        self.assertFalse(flags["is_company_admin"])
        self.assertFalse(flags["is_team_admin"])

    def test_superuser_all_true_via_ladder(self):
        admin = make_superuser(company=self.company)
        request = self.factory.get("/")
        request.user = admin
        request.company = self.company
        flags = auth_flags(request)
        # Platform admin > company admin > team admin. A superuser is
        # the top of the ladder, so all three rungs are true.
        self.assertTrue(flags["is_platform_admin"])
        self.assertTrue(flags["is_company_admin"])
        self.assertTrue(flags["is_team_admin"])

    def test_platform_admin_group_all_true(self):
        user = make_staff_user(company=self.company)
        mgmt, _ = Group.objects.get_or_create(name="Platform Admin")
        user.groups.add(mgmt)
        request = self.factory.get("/")
        request.user = user
        request.company = self.company
        flags = auth_flags(request)
        self.assertTrue(flags["is_platform_admin"])
        # Platform admin implies company admin and team admin via the ladder
        self.assertTrue(flags["is_company_admin"])
        self.assertTrue(flags["is_team_admin"])
