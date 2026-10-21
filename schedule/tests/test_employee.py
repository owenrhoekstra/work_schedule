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
        self.assertIn("identity_form", resp.context)
        self.assertIn("current_pattern", resp.context)
        self.assertIn("patterns", resp.context)


@override_settings(CACHES=_LOCMEM_CACHES)
class EmployeeIdentityFormTests(TestCase):
    def setUp(self):
        self.user = make_manager_user()
        from django.contrib.auth.models import Group, Permission

        mgmt = Group.objects.get_or_create(name="Management")[0]
        mgmt.permissions.set(Permission.objects.all())
        self.user.groups.add(mgmt)
        self.client.force_login(self.user)
        self.role = make_role(name="Receptionist", order=20)
        self.emp = make_employee(role=self.role)

    def post_identity(self, **overrides):
        data = {
            "form": "identity",
            "title": "",
            "first_name": "Updated",
            "last_name": "Name",
            "role": str(self.role.pk),
            "email": self.emp.email,
            "start_date": self.emp.start_date.isoformat(),
        }
        data.update(overrides)
        return self.client.post(reverse("employee_defaults", args=[self.emp.pk]), data)

    def test_basic_update(self):
        resp = self.post_identity(first_name="New")
        self.assertEqual(resp.status_code, 302)
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.first_name, "New")

    def test_start_date_change_syncs_period(self):
        new = date(2026, 1, 15)
        resp = self.post_identity(start_date=new.isoformat())
        self.assertEqual(resp.status_code, 302)
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.start_date, new)
        self.assertEqual(self.emp.periods.first().start_date, new)

    def test_start_after_period_end_rejected(self):
        period = self.emp.periods.first()
        period.end_date = date(2026, 6, 1)
        period.save()
        resp = self.post_identity(start_date="2026-07-01")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["identity_form"].errors)

    def test_duplicate_email_rejected(self):
        other = make_employee(email="other@x.com")
        resp = self.post_identity(email=other.email)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["identity_form"].errors)

    # ----- earliest-pattern sliding -----

    def test_start_date_earlier_slides_earliest_pattern_backward(self):
        pattern = self.emp.patterns.first()
        pattern.effective_from = date(2025, 6, 2)
        pattern.save(update_fields=["effective_from"])

        new_start = date(2024, 11, 7)
        resp = self.post_identity(start_date=new_start.isoformat())
        self.assertEqual(resp.status_code, 302)

        pattern.refresh_from_db()
        self.assertEqual(pattern.effective_from, date(2024, 11, 4))

    def test_start_date_later_slides_earliest_pattern_forward_when_no_collision(
        self,
    ):
        self.emp.patterns.all().delete()
        ShiftPattern.objects.create(
            employee=self.emp, effective_from=date(2025, 1, 6), cycle_weeks=1
        )
        ShiftPattern.objects.create(
            employee=self.emp, effective_from=date(2025, 6, 2), cycle_weeks=1
        )

        resp = self.post_identity(start_date=date(2025, 3, 1).isoformat())
        self.assertEqual(resp.status_code, 302)

        earliest = self.emp.patterns.order_by("effective_from").first()
        self.assertEqual(earliest.effective_from, date(2025, 2, 24))

    def test_start_date_later_does_not_collide_with_next_pattern(self):
        self.emp.patterns.all().delete()
        ShiftPattern.objects.create(
            employee=self.emp, effective_from=date(2025, 1, 6), cycle_weeks=1
        )
        ShiftPattern.objects.create(
            employee=self.emp, effective_from=date(2025, 2, 3), cycle_weeks=1
        )

        resp = self.post_identity(start_date=date(2025, 2, 10).isoformat())
        self.assertEqual(resp.status_code, 302)

        earliest = self.emp.patterns.order_by("effective_from").first()
        self.assertEqual(earliest.effective_from, date(2025, 1, 6))
