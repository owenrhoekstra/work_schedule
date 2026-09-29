from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, Group, User
from django.test import RequestFactory, TestCase, override_settings

from accounts.context_processors import pending_accounts, user_is_management

from .factories import make_employee, make_staff_user, make_superuser

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


@override_settings(CACHES=_LOCMEM_CACHES)
class PendingAccountsContextTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_anonymous_returns_empty(self):
        request = self.factory.get("/")
        request.user = AnonymousUser()
        self.assertEqual(pending_accounts(request), {})

    def test_staff_without_add_employee_permission(self):
        user = make_staff_user("plain")
        request = self.factory.get("/")
        request.user = user
        self.assertEqual(pending_accounts(request), {})

    def test_manager_sees_count(self):
        admin = make_superuser()
        emp = make_employee(email="pend@example.com")
        pending = User.objects.create_user(
            username="pend",
            password="p",
            email=emp.email,
            is_active=False,
        )
        emp.user = pending
        emp.save()
        request = self.factory.get("/")
        request.user = admin
        self.assertEqual(pending_accounts(request)["pending_accounts_count"], 1)

    def test_db_error_returns_empty(self):
        """If the DB query fails, don't blow up the page."""
        admin = make_superuser()
        request = self.factory.get("/")
        request.user = admin
        with patch("accounts.context_processors.User.objects") as mock_mgr:
            mock_mgr.filter.side_effect = Exception("db down")
            self.assertEqual(pending_accounts(request), {})


@override_settings(CACHES=_LOCMEM_CACHES)
class UserIsManagementContextTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_anonymous_false(self):
        request = self.factory.get("/")
        request.user = AnonymousUser()
        self.assertFalse(user_is_management(request)["is_management"])

    def test_plain_user_false(self):
        user = make_staff_user()
        request = self.factory.get("/")
        request.user = user
        self.assertFalse(user_is_management(request)["is_management"])

    def test_superuser_true(self):
        admin = make_superuser()
        request = self.factory.get("/")
        request.user = admin
        self.assertTrue(user_is_management(request)["is_management"])

    def test_management_group_true(self):
        user = make_staff_user()
        mgmt = Group.objects.create(name="Management")
        user.groups.add(mgmt)
        request = self.factory.get("/")
        request.user = user
        self.assertTrue(user_is_management(request)["is_management"])
