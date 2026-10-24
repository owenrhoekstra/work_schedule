"""Regression coverage for Session 5.5 (BUG-001, BUG-002).

BUG-002: prefill panels used to be indexed by target cycle offset,
but target offset 0 is not calendar week effective_from when
effective_from isn't congruent with CYCLE_EPOCH. Manager edits to
"Week A" landed on a different calendar week than the one being
looked at.

BUG-001: the split branch's notification baseline was `old_shifts = {}`,
reporting every change as OFF→new instead of old→new.
"""

from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from schedule.models import Shift, ShiftPattern
from schedule.views import _grid_weeks_for_form

from .factories import make_employee, make_staff_user, make_superuser

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


def _monday(d):
    return d - timedelta(days=d.weekday())


@override_settings(CACHES=_LOCMEM_CACHES)
class GridPrefillAlignmentTests(TestCase):
    """BUG-002: panel index = calendar week, not target cycle offset."""

    def test_prefill_shows_calendar_week_not_target_offset_zero(self):
        # CYCLE_EPOCH is 2026-01-05. epoch + 1 week has cycle-offset 1
        # under a 2-week cycle.
        epoch = settings.CYCLE_EPOCH
        target_week = epoch + timedelta(weeks=1)

        emp = make_employee(start_date=epoch)
        emp.patterns.all().delete()
        p = ShiftPattern.objects.create(
            employee=emp,
            effective_from=epoch,
            cycle_weeks=2,
            effective_to=None,
        )
        Shift.objects.create(
            pattern=p,
            week_offset=0,
            day=0,
            start_time="09:00",
            end_time="17:00",
        )
        Shift.objects.create(
            pattern=p,
            week_offset=1,
            day=0,
            start_time="10:00",
            end_time="18:00",
        )

        weeks = _grid_weeks_for_form(emp, target_week, 2)
        # Panel 0 (calendar week target_week) must show P.shifts[1]
        # (10:00), not P.shifts[0].
        self.assertEqual(
            weeks[0]["rows"][0]["shift"].start_time.strftime("%H:%M"),
            "10:00",
        )
        # Panel 1 (calendar week target_week + 7d) must show P.shifts[0].
        self.assertEqual(
            weeks[1]["rows"][0]["shift"].start_time.strftime("%H:%M"),
            "09:00",
        )


@override_settings(CACHES=_LOCMEM_CACHES)
class ChangeEditLandsOnVisibleWeekTests(TestCase):
    """BUG-002: saving must persist edits to the panel's calendar week."""

    def setUp(self):
        self.admin = make_superuser()
        self.client.force_login(self.admin)

    def test_edit_in_place_edit_lands_on_visible_week(self):
        epoch = settings.CYCLE_EPOCH
        target_week = epoch + timedelta(weeks=1)  # cycle-offset 1

        emp = make_employee(start_date=epoch)
        emp.patterns.all().delete()
        p = ShiftPattern.objects.create(
            employee=emp,
            effective_from=target_week,  # edit-in-place at this week
            cycle_weeks=2,
            effective_to=None,
        )
        Shift.objects.create(
            pattern=p,
            week_offset=0,
            day=0,
            start_time="09:00",
            end_time="17:00",
        )
        Shift.objects.create(
            pattern=p,
            week_offset=1,
            day=0,
            start_time="10:00",
            end_time="18:00",
        )

        resp = self.client.post(
            reverse("schedule_change", args=[emp.pk]),
            {
                "effective_from": target_week.isoformat(),
                "cycle_weeks": "2",
                "retroactive_confirmed": "1",
                "week_0_day_0_start": "08:00",
                "week_0_day_0_end": "16:00",
                # Panel 1 cleared (OFF).
                "week_1_day_0_start": "",
                "week_1_day_0_end": "",
            },
        )
        self.assertEqual(resp.status_code, 302)

        target = ShiftPattern.objects.get(pk=p.pk)
        # Panel 0 must land at offset 1 (base_target_offset for
        # target_week under cycle 2).
        shift_at_1 = Shift.objects.get(pattern=target, week_offset=1, day=0)
        self.assertEqual(shift_at_1.start_time.strftime("%H:%M"), "08:00")
        # Panel 1 must land at offset 0 and be OFF (cleared).
        self.assertFalse(
            Shift.objects.filter(
                pattern=target, week_offset=0, day=0
            ).exists()
        )


@override_settings(CACHES=_LOCMEM_CACHES)
class SplitNotificationBaselineTests(TestCase):
    """BUG-001: split-branch notification shows old→new, not OFF→new."""

    def setUp(self):
        self.admin = make_superuser()
        self.client.force_login(self.admin)
        # The notification path short-circuits on eligibility before
        # reaching send_email. To exercise the diff content, the
        # employee must be an eligible recipient — i.e. linked to an
        # active user. Mirrors the pattern used by other notification
        # tests (see test_views_edges.SetOverrideEdgeTests and
        # test_deactivate_with_notify).
        self.emp_user = make_staff_user("splitnotify")

    @patch("schedule.notifications.send_email")
    def test_split_branch_notification_baseline_is_calendar_aligned(
        self, mock_send
    ):
        epoch = settings.CYCLE_EPOCH
        split_week = epoch + timedelta(weeks=2)  # cycle-offset 0

        emp = make_employee(start_date=epoch)
        emp.patterns.all().delete()
        emp.user = self.emp_user
        emp.save(update_fields=["user"])
        p = ShiftPattern.objects.create(
            employee=emp,
            effective_from=epoch,
            cycle_weeks=2,
            effective_to=None,
        )
        Shift.objects.create(
            pattern=p,
            week_offset=0,
            day=0,
            start_time="09:00",
            end_time="17:00",
        )
        Shift.objects.create(
            pattern=p,
            week_offset=1,
            day=0,
            start_time="10:00",
            end_time="18:00",
        )

        resp = self.client.post(
            reverse("schedule_change", args=[emp.pk]),
            {
                "effective_from": split_week.isoformat(),
                "cycle_weeks": "2",
                "retroactive_confirmed": "1",
                "notify": "1",
                "week_0_day_0_start": "08:00",
                "week_0_day_0_end": "16:00",
                "week_1_day_0_start": "11:00",
                "week_1_day_0_end": "19:00",
            },
        )
        self.assertEqual(resp.status_code, 302)
        mock_send.assert_called_once()

        changes = mock_send.call_args.kwargs["context"]["changes"]
        by_label = {c["label"]: c for c in changes}

        # Week A Monday: old 9-5 → new 8-4 (baseline was pattern's
        # offset 0, not empty).
        self.assertIn("Week A Monday", by_label)
        self.assertEqual(
            by_label["Week A Monday"]["old"], "9:00 AM – 5:00 PM"
        )
        self.assertEqual(
            by_label["Week A Monday"]["new"], "8:00 AM – 4:00 PM"
        )
        # Week B Monday: old 10-6 → new 11-7.
        self.assertIn("Week B Monday", by_label)
        self.assertEqual(
            by_label["Week B Monday"]["old"], "10:00 AM – 6:00 PM"
        )
        self.assertEqual(
            by_label["Week B Monday"]["new"], "11:00 AM – 7:00 PM"
        )