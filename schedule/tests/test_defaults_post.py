from datetime import date

from django.test import TestCase, override_settings
from django.urls import reverse

from schedule.models import Shift, ShiftPattern

from .factories import make_employee, make_manager_user, make_role


_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


def _make_manager(username="mgr_defaults"):
    from django.contrib.auth.models import Group, Permission

    user = make_manager_user(username)
    mgmt, _ = Group.objects.get_or_create(name="Management")
    mgmt.permissions.set(Permission.objects.all())
    user.groups.add(mgmt)
    return user


@override_settings(CACHES=_LOCMEM_CACHES)
class DefaultsPostEditOrSplitTests(TestCase):
    def setUp(self):
        self.client.force_login(_make_manager())
        self.role = make_role("Receptionist", order=20)
        self.emp = make_employee(
            role=self.role, start_date=date(2025, 1, 1)
        )
        # Remove the signal-created initial pattern so we control the
        # starting state.
        self.emp.patterns.all().delete()

    def _post(self, effective_from, shifts=None, cycle_weeks=1, **overrides):
        data = {
            "form": "defaults",
            "cycle_weeks": str(cycle_weeks),
            "effective_from": effective_from.isoformat(),
        }
        if shifts:
            for (week_offset, day), (start, end) in shifts.items():
                data[f"week_{week_offset}_day_{day}_start"] = start
                data[f"week_{week_offset}_day_{day}_end"] = end
        data.update(overrides)
        return self.client.post(
            reverse("employee_defaults", args=[self.emp.pk]), data
        )

    # ----- edit in place -----

    def test_submit_at_existing_pattern_date_edits_in_place(self):
        pattern = ShiftPattern.objects.create(
            employee=self.emp,
            effective_from=date(2025, 6, 2),
            cycle_weeks=1,
        )
        Shift.objects.create(
            pattern=pattern,
            week_offset=0,
            day=0,
            start_time="09:00",
            end_time="17:00",
        )
        self._post(
            date(2025, 6, 2),
            shifts={(0, 0): ("10:00", "18:00")},
            retroactive_confirmed="1",
        )
        self.assertEqual(self.emp.patterns.count(), 1)
        pattern.refresh_from_db()
        shift = pattern.shifts.get(week_offset=0, day=0)
        self.assertEqual(shift.start_time.strftime("%H:%M"), "10:00")

    # ----- split -----

    def test_submit_inside_pattern_range_splits_pattern(self):
        ShiftPattern.objects.create(
            employee=self.emp,
            effective_from=date(2025, 6, 2),
            cycle_weeks=1,
        )
        # Add a shift so this isn't considered first-time setup, forcing
        # the retroactive guard.
        Shift.objects.create(
            pattern=self.emp.patterns.first(),
            week_offset=0,
            day=0,
            start_time="09:00",
            end_time="17:00",
        )
        self._post(
            date(2025, 7, 7),
            shifts={(0, 0): ("09:00", "17:00")},
            retroactive_confirmed="1",
        )
        self.assertEqual(self.emp.patterns.count(), 2)
        patterns = list(self.emp.patterns.order_by("effective_from"))
        self.assertEqual(patterns[0].effective_from, date(2025, 6, 2))
        self.assertEqual(patterns[0].effective_to, date(2025, 7, 7))
        self.assertEqual(patterns[1].effective_from, date(2025, 7, 7))
        self.assertIsNone(patterns[1].effective_to)

    def test_split_inherits_effective_to(self):
        ShiftPattern.objects.create(
            employee=self.emp,
            effective_from=date(2025, 6, 2),
            effective_to=date(2025, 9, 1),
            cycle_weeks=1,
        )
        ShiftPattern.objects.create(
            employee=self.emp,
            effective_from=date(2025, 9, 1),
            cycle_weeks=1,
        )
        Shift.objects.create(
            pattern=self.emp.patterns.first(),
            week_offset=0,
            day=0,
            start_time="09:00",
            end_time="17:00",
        )
        self._post(
            date(2025, 7, 7),
            shifts={(0, 0): ("09:00", "17:00")},
            retroactive_confirmed="1",
        )
        patterns = list(self.emp.patterns.order_by("effective_from"))
        self.assertEqual(len(patterns), 3)
        self.assertEqual(patterns[1].effective_from, date(2025, 7, 7))
        self.assertEqual(patterns[1].effective_to, date(2025, 9, 1))

    def test_split_earliest_allowed(self):
        ShiftPattern.objects.create(
            employee=self.emp,
            effective_from=date(2025, 6, 2),
            cycle_weeks=1,
        )
        Shift.objects.create(
            pattern=self.emp.patterns.first(),
            week_offset=0,
            day=0,
            start_time="09:00",
            end_time="17:00",
        )
        self._post(
            date(2025, 7, 7),
            shifts={(0, 0): ("09:00", "17:00")},
            retroactive_confirmed="1",
        )
        self.assertEqual(self.emp.patterns.count(), 2)

    # ----- create -----

    def test_create_when_no_pattern_covers(self):
        # No shifts anywhere → first-time setup, retroactive guard is
        # bypassed even though the date is in the past.
        self._post(
            date(2025, 6, 2),
            shifts={(0, 0): ("09:00", "17:00")},
        )
        self.assertEqual(self.emp.patterns.count(), 1)
        pattern = self.emp.patterns.first()
        self.assertEqual(pattern.effective_from, date(2025, 6, 2))
        self.assertIsNone(pattern.effective_to)

    # ----- retroactive guard -----

    def test_retroactive_requires_confirmation(self):
        pattern = ShiftPattern.objects.create(
            employee=self.emp,
            effective_from=date(2025, 3, 3),
            cycle_weeks=1,
        )
        Shift.objects.create(
            pattern=pattern,
            week_offset=0,
            day=0,
            start_time="09:00",
            end_time="17:00",
        )
        resp = self._post(
            date(2025, 4, 7),
            shifts={(0, 0): ("10:00", "18:00")},
        )
        # The guard re-renders the page with an error message (200)
        # rather than redirecting, so the user's form input is
        # preserved when the confirmation dialog is bypassed or JS is
        # disabled.
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Confirm the retroactive change")

        # Nothing was written.
        self.assertEqual(self.emp.patterns.count(), 1)
        shift = pattern.shifts.get(week_offset=0, day=0)
        self.assertEqual(shift.start_time.strftime("%H:%M"), "09:00")

    def test_retroactive_with_confirmation_writes(self):
        pattern = ShiftPattern.objects.create(
            employee=self.emp,
            effective_from=date(2025, 3, 3),
            cycle_weeks=1,
        )
        Shift.objects.create(
            pattern=pattern,
            week_offset=0,
            day=0,
            start_time="09:00",
            end_time="17:00",
        )
        self._post(
            date(2025, 4, 7),
            shifts={(0, 0): ("10:00", "18:00")},
            retroactive_confirmed="1",
        )
        # 2025-04-07 is inside the 2025-03-03 open pattern → split.
        self.assertEqual(self.emp.patterns.count(), 2)

    def test_no_shifts_bypasses_retroactive_even_with_patterns(self):
        # An empty pattern exists but no shifts — still first-time
        # setup from the guard's perspective.
        ShiftPattern.objects.create(
            employee=self.emp,
            effective_from=date(2025, 6, 2),
            cycle_weeks=1,
        )
        self._post(
            date(2025, 6, 2),
            shifts={(0, 0): ("09:00", "17:00")},
        )
        pattern = self.emp.patterns.first()
        self.assertEqual(
            pattern.shifts.get(week_offset=0, day=0).start_time.strftime("%H:%M"),
            "09:00",
        )