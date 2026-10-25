"""Coverage for the calendar week picker (Session 6.5).

The picker itself is client-side Alpine; Django tests cover the
template presence, context values, and edit-mode static rendering.
"""

from datetime import date, timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from schedule.views import _week_start

from .factories import make_employee, make_manager_user

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


@override_settings(CACHES=_LOCMEM_CACHES)
class WeekPickerModalTests(TestCase):
    def setUp(self):
        self.user = make_manager_user()
        self.client.force_login(self.user)
        self.emp = make_employee(with_pattern=True)

    def test_change_mode_includes_picker_modal(self):
        resp = self.client.get(reverse("schedule_change", args=[self.emp.pk]))
        self.assertContains(resp, 'id="week-picker-modal"')

    def test_add_mode_includes_picker_modal(self):
        resp = self.client.get(reverse("schedule_add", args=[self.emp.pk]))
        self.assertContains(resp, 'id="week-picker-modal"')

    def test_edit_mode_excludes_picker_modal(self):
        pattern = self.emp.patterns.order_by("effective_from").first()
        resp = self.client.get(
            reverse("pattern_edit", args=[self.emp.pk, pattern.pk])
        )
        self.assertNotContains(resp, 'id="week-picker-modal"')

    def test_edit_mode_shows_static_week_label(self):
        pattern = self.emp.patterns.order_by("effective_from").first()
        resp = self.client.get(
            reverse("pattern_edit", args=[self.emp.pk, pattern.pk])
        )
        # Static display, no trigger button
        self.assertNotContains(resp, 'id="week-picker-trigger"')
        # Label appears in the picker row
        self.assertContains(resp, "Week of")


@override_settings(CACHES=_LOCMEM_CACHES)
class WeekPickerContextTests(TestCase):
    def setUp(self):
        self.user = make_manager_user()
        self.client.force_login(self.user)

    def test_week_picker_min_iso_is_employee_start_monday(self):
        emp = make_employee(start_date=date(2026, 3, 4))  # Wednesday
        resp = self.client.get(reverse("schedule_change", args=[emp.pk]))
        expected = _week_start(date(2026, 3, 4)).isoformat()  # Monday 2026-03-02
        self.assertEqual(resp.context["week_picker_min_iso"], expected)

    def test_today_iso_is_today(self):
        emp = make_employee()
        resp = self.client.get(reverse("schedule_change", args=[emp.pk]))
        self.assertEqual(
            resp.context["today_iso"], timezone.localdate().isoformat()
        )

    def test_week_options_removed_from_context(self):
        emp = make_employee()
        resp = self.client.get(reverse("schedule_change", args=[emp.pk]))
        self.assertNotIn("week_options", resp.context)

    def test_effective_from_label_formatted(self):
        emp = make_employee(start_date=date(2026, 10, 19))
        resp = self.client.get(reverse("schedule_change", args=[emp.pk]))
        # Change mode defaults to this week; label should be present
        self.assertIn("effective_from_label", resp.context)
        self.assertIn("Week of", resp.context["effective_from_label"])

    def test_trigger_has_data_attributes(self):
        emp = make_employee(start_date=date(2026, 10, 19))
        resp = self.client.get(reverse("schedule_change", args=[emp.pk]))
        self.assertContains(resp, 'id="week-picker-trigger"')
        self.assertContains(resp, 'data-selected="')
        self.assertContains(resp, 'data-min="')