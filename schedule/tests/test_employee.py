from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from schedule.models import Shift, ShiftPattern

from .factories import make_employee, make_manager_user, make_role, make_staff_user

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


@override_settings(CACHES=_LOCMEM_CACHES)
class EmployeePageGetTests(TestCase):
    def setUp(self):
        self.user = make_manager_user()
        from django.contrib.auth.models import Group, Permission

        mgmt = Group.objects.create(name="Management")
        mgmt.permissions.set(Permission.objects.all())
        self.user.groups.add(mgmt)
        self.client.force_login(self.user)
        self.role = make_role(name="Receptionist", order=20)
        self.emp = make_employee(role=self.role)

    def test_staff_without_view_employee_gets_403(self):
        self.client.logout()
        self.client.force_login(make_staff_user("staff2"))
        resp = self.client.get(reverse("employee_defaults", args=[self.emp.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_inactive_employee_returns_404(self):
        self.emp.is_active = False
        self.emp.last_day = date.today() - timedelta(days=1)
        self.emp.save()
        resp = self.client.get(reverse("employee_defaults", args=[self.emp.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_get_renders_reading_page(self):
        resp = self.client.get(reverse("employee_defaults", args=[self.emp.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("current_pattern", resp.context)
        self.assertIn("patterns", resp.context)
