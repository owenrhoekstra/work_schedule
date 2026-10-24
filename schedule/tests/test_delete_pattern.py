"""Regression coverage for the delete_pattern view.

Deleting a middle pattern used to leave every week in its range
uncovered — `_pattern_for_week` returned None and every day in that
window rendered as OFF. The view now extends the predecessor's
`effective_to` to the deleted pattern's `effective_to` before deleting,
so the range stays continuous.
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from schedule.models import Employee, Role, ShiftPattern

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


def _monday(d):
    return d - timedelta(days=d.weekday())


@override_settings(CACHES=_LOCMEM_CACHES)
class DeletePatternTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="x"
        )
        self.client.force_login(self.user)

        self.role = Role.objects.create(name="Test Role")
        self.employee = Employee.objects.create(
            first_name="Test",
            last_name="Employee",
            role=self.role,
            email="test@example.com",
            start_date=_monday(timezone.localdate()) - timedelta(weeks=8),
        )
        # ensure_employee_has_pattern created a starter pattern. Drop it
        # so the three patterns below are the only ones in play.
        self.employee.patterns.all().delete()

        self.wk0 = _monday(timezone.localdate()) - timedelta(weeks=8)
        self.wk1 = self.wk0 + timedelta(weeks=4)
        self.wk2 = self.wk1 + timedelta(weeks=4)

        self.pattern_a = ShiftPattern.objects.create(
            employee=self.employee,
            effective_from=self.wk0,
            effective_to=self.wk1,
            cycle_weeks=1,
        )
        self.pattern_b = ShiftPattern.objects.create(
            employee=self.employee,
            effective_from=self.wk1,
            effective_to=self.wk2,
            cycle_weeks=1,
        )
        self.pattern_c = ShiftPattern.objects.create(
            employee=self.employee,
            effective_from=self.wk2,
            effective_to=None,
            cycle_weeks=1,
        )

    def test_deleting_middle_pattern_extends_predecessor(self):
        url = reverse("delete_pattern", args=[self.pattern_b.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

        self.assertFalse(
            ShiftPattern.objects.filter(pk=self.pattern_b.pk).exists()
        )
        self.pattern_a.refresh_from_db()
        self.assertEqual(self.pattern_a.effective_to, self.wk2)

    def test_deleting_open_ended_pattern_extends_predecessor_to_none(self):
        # Remove C first so B can be open-ended.
        self.pattern_c.delete()
        self.pattern_b.effective_to = None
        self.pattern_b.save(update_fields=["effective_to"])

        url = reverse("delete_pattern", args=[self.pattern_b.pk])
        self.client.post(url)

        self.pattern_a.refresh_from_db()
        self.assertIsNone(self.pattern_a.effective_to)

    def test_cannot_delete_earliest_pattern(self):
        url = reverse("delete_pattern", args=[self.pattern_a.pk])
        self.client.post(url)

        self.assertTrue(
            ShiftPattern.objects.filter(pk=self.pattern_a.pk).exists()
        )