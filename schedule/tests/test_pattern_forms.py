from datetime import date

from django.test import TestCase, override_settings
from django.urls import reverse

from schedule.models import Shift, ShiftPattern

from .factories import make_employee, make_manager_user, make_role


_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


def _make_manager(username="mgr_forms"):
    from django.contrib.auth.models import Group, Permission

    user = make_manager_user(username)
    mgmt, _ = Group.objects.get_or_create(name="Management")
    mgmt.permissions.set(Permission.objects.all())
    user.groups.add(mgmt)
    return user


@override_settings(CACHES=_LOCMEM_CACHES)
class PatternFormViewTests(TestCase):
    def setUp(self):
        self.client.force_login(_make_manager())
        self.role = make_role("Receptionist", order=20)
        self.emp = make_employee(
            role=self.role, start_date=date(2025, 1, 1)
        )
        self.emp.patterns.all().delete()

    def _post(self, url_name, effective_from, shifts=None, cycle_weeks=1, **overrides):
        data = {
            "cycle_weeks": str(cycle_weeks),
            "effective_from": effective_from.isoformat(),
        }
        if shifts:
            for (week_offset, day), (start, end) in shifts.items():
                data[f"week_{week_offset}_day_{day}_start"] = start
                data[f"week_{week_offset}_day_{day}_end"] = end
        data.update(overrides)
        return self.client.post(
            reverse(url_name, args=[self.emp.pk]), data
        )

    # ----- schedule_change -----

    def test_change_get_renders(self):
        resp = self.client.get(reverse("schedule_change", args=[self.emp.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Change schedule")

    def test_change_create_pattern(self):
        self._post(
            "schedule_change",
            date(2025, 6, 2),
            shifts={(0, 0): ("09:00", "17:00")},
        )
        self.assertEqual(self.emp.patterns.count(), 1)
        p = self.emp.patterns.first()
        self.assertEqual(p.effective_from, date(2025, 6, 2))
        self.assertIsNone(p.effective_to)

    def test_change_split_pattern(self):
        p = ShiftPattern.objects.create(
            employee=self.emp,
            effective_from=date(2025, 6, 2),
            cycle_weeks=1,
        )
        Shift.objects.create(
            pattern=p, week_offset=0, day=0,
            start_time="09:00", end_time="17:00",
        )
        self._post(
            "schedule_change",
            date(2025, 7, 7),
            shifts={(0, 0): ("10:00", "18:00")},
            retroactive_confirmed="1",
        )
        self.assertEqual(self.emp.patterns.count(), 2)
        patterns = list(self.emp.patterns.order_by("effective_from"))
        self.assertEqual(patterns[0].effective_to, date(2025, 7, 7))
        self.assertEqual(patterns[1].effective_from, date(2025, 7, 7))

    def test_change_retroactive_requires_confirmation(self):
        p = ShiftPattern.objects.create(
            employee=self.emp,
            effective_from=date(2025, 3, 3),
            cycle_weeks=1,
        )
        Shift.objects.create(
            pattern=p, week_offset=0, day=0,
            start_time="09:00", end_time="17:00",
        )
        resp = self._post(
            "schedule_change",
            date(2025, 4, 7),
            shifts={(0, 0): ("10:00", "18:00")},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "in the past")
        self.assertEqual(self.emp.patterns.count(), 1)

    def test_change_retroactive_with_confirmation(self):
        p = ShiftPattern.objects.create(
            employee=self.emp,
            effective_from=date(2025, 3, 3),
            cycle_weeks=1,
        )
        Shift.objects.create(
            pattern=p, week_offset=0, day=0,
            start_time="09:00", end_time="17:00",
        )
        self._post(
            "schedule_change",
            date(2025, 4, 7),
            shifts={(0, 0): ("10:00", "18:00")},
            retroactive_confirmed="1",
        )
        self.assertEqual(self.emp.patterns.count(), 2)

    def test_change_preserves_valid_cells_on_validation_error(self):
        # BUG-003: one bad cell shouldn't wipe the rest of the grid.
        # is_first_time=True (setUp has no patterns), so the
        # retroactive guard is bypassed; the grid validation error
        # fires first.
        resp = self._post(
            "schedule_change",
            date(2025, 6, 2),
            shifts={(0, 0): ("09:00", "17:00")},
            week_0_day_1_start="garbage",
            week_0_day_1_end="17:00",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Could not understand")
        html = resp.content.decode()
        # Valid cell preserved (unique value appears exactly once)
        self.assertEqual(html.count('value="9:00 AM"'), 1)
        # The invalid cell's parse-failed start is empty in the re-render.
        self.assertEqual(html.count('value="garbage"'), 0)
        # Nothing was saved.
        self.assertEqual(self.emp.patterns.count(), 0)

    def test_change_preserves_cells_after_first_error(self):
        # BUG-003: previous code returned on first error, dropping
        # values for cells after the error.
        resp = self._post(
            "schedule_change",
            date(2025, 6, 2),
            shifts={
                (0, 0): ("09:00", "17:00"),  # valid, before error
                (0, 2): ("08:00", "16:00"),  # valid, after error
            },
            week_0_day_1_start="garbage",  # error between them
            week_0_day_1_end="17:00",
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertEqual(html.count('value="9:00 AM"'), 1)
        self.assertEqual(html.count('value="8:00 AM"'), 1)

    # ----- schedule_add -----

    def test_add_get_renders_with_no_week(self):
        resp = self.client.get(reverse("schedule_add", args=[self.emp.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Pick a week")

    def test_add_create_pattern(self):
        self._post(
            "schedule_add",
            date(2025, 8, 4),
            shifts={(0, 0): ("09:00", "17:00")},
        )
        self.assertEqual(self.emp.patterns.count(), 1)
        self.assertEqual(self.emp.patterns.first().effective_from, date(2025, 8, 4))

    # ----- preview endpoint -----

    def test_preview_returns_body(self):
        resp = self.client.get(
            reverse("pattern_form_preview", args=[self.emp.pk]),
            {"effective_from": "2025-06-02", "cycle_weeks": "1", "mode": "change"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "pattern-form-body")

    def test_preview_no_week_prompts_pick(self):
        resp = self.client.get(
            reverse("pattern_form_preview", args=[self.emp.pk]),
            {"mode": "add"},
        )
        self.assertContains(resp, "Pick a week")

    def test_change_includes_save_pattern_modal(self):
        resp = self.client.get(reverse("schedule_change", args=[self.emp.pk]))
        self.assertContains(resp, 'id="confirm-save-pattern-modal"')

    def test_add_includes_save_pattern_modal(self):
        resp = self.client.get(reverse("schedule_add", args=[self.emp.pk]))
        self.assertContains(resp, 'id="confirm-save-pattern-modal"')

    def test_cancel_uses_discard_modal(self):
        resp = self.client.get(reverse("schedule_change", args=[self.emp.pk]))
        self.assertContains(resp, "openConfirmDiscardModal(")