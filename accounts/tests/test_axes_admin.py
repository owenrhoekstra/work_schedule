"""SEC-006 finding #4: Axes admin add-permission override.

Django's default ModelAdmin.has_add_permission checks only the
model's add permission. A non-superuser staff user holding
axes.add_accessattempt could create authentication records via
admin, forging failure counters that affect lockout decisions.

The custom Axes admin classes in accounts/admin.py override every
other permission to superuser-only. has_add_permission was the gap.
"""

from django.contrib import admin
from django.contrib.auth.models import Permission, User
from django.test import TestCase

from axes.models import AccessAttempt, AccessLog

from schedule.tests.factories import make_superuser


def _fake_request(user):
    """Minimal stand-in for a Django request for permission-method tests."""
    return type("Req", (), {"user": user})()


def _make_staff_with_axes_add(username):
    """A non-superuser staff user holding both Axes add permissions.

    Without our has_add_permission override, Django's default checks
    only the model permission, so this user would be allowed to add
    AccessAttempt / AccessLog rows through the admin. That's the exact
    scenario the finding describes.
    """
    user = User.objects.create_user(
        username=username,
        password="p",
        is_staff=True,
        is_active=True,
    )
    for codename in ("add_accessattempt", "add_accesslog"):
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return user


class AxesAdminAddPermissionTests(TestCase):
    def test_staff_with_add_perm_cannot_add_attempt(self):
        user = _make_staff_with_axes_add("axesstaff")
        ma = admin.site._registry[AccessAttempt]
        self.assertFalse(ma.has_add_permission(_fake_request(user)))

    def test_staff_with_add_perm_cannot_add_log(self):
        user = _make_staff_with_axes_add("axesstaff2")
        ma = admin.site._registry[AccessLog]
        self.assertFalse(ma.has_add_permission(_fake_request(user)))

    def test_superuser_can_add_attempt(self):
        user = make_superuser("axessuper")
        ma = admin.site._registry[AccessAttempt]
        self.assertTrue(ma.has_add_permission(_fake_request(user)))

    def test_superuser_can_add_log(self):
        user = make_superuser("axessuper2")
        ma = admin.site._registry[AccessLog]
        self.assertTrue(ma.has_add_permission(_fake_request(user)))