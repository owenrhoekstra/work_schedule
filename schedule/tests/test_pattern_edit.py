"""Coverage for the pattern edit page (Session 6)."""

from datetime import timedelta

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from schedule.models import Shift, ShiftPattern

from .factories import make_employee, make_manager_user

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


def _monday(d):
    return d - timedelta(days=d.weekday())


@override_settings(CACHES=_LOCMEM_CACHES)
class PatternEditGetTests(TestCase):
    def setUp(self):
        self.user = make_manager_user()
        self.client.force_login(self.user)
        self.emp = make_employee(with_pattern=True)
        self.pattern = self.emp.patterns.order_by("effective_from").first()

    def test_renders_edit_form(self):
        resp = self.client.get(
            reverse("pattern_edit", args=[self.emp.pk, self.pattern.pk])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["mode"], "edit")
        self.assertTrue(resp.context["is_earliest_pattern"])

    def test_404_for_wrong_employee(self):
        other = make_employee(email="other@example.com")
        resp = self.client.get(
            reverse("pattern_edit", args=[other.pk, self.pattern.pk])
        )
        self.assertEqual(resp.status_code, 404)

    def test_delete_button_hidden_on_earliest(self):
        resp = self.client.get(
            reverse("pattern_edit", args=[self.emp.pk, self.pattern.pk])
        )
        self.assertNotContains(resp, "delete-pattern-form")

    def test_delete_button_shown_on_non_earliest(self):
        later = ShiftPattern.objects.create(
            employee=self.emp,
            effective_from=_monday(timezone.localdate()) + timedelta(weeks=2),
            effective_to=None,
        )
        resp = self.client.get(reverse("pattern_edit", args=[self.emp.pk, later.pk]))
        self.assertContains(resp, "delete-pattern-form")

    def test_retroactive_modal_rendered_on_past_pattern(self):
        self.pattern.effective_from = _monday(timezone.localdate()) - timedelta(weeks=4)
        self.pattern.save(update_fields=["effective_from"])
        resp = self.client.get(
            reverse("pattern_edit", args=[self.emp.pk, self.pattern.pk])
        )
        self.assertContains(resp, 'id="retroactive-confirm-modal"')

    def test_retroactive_modal_not_rendered_on_future_pattern(self):
        future = _monday(timezone.localdate()) + timedelta(weeks=4)
        self.pattern.effective_from = future
        self.pattern.save(update_fields=["effective_from"])
        resp = self.client.get(
            reverse("pattern_edit", args=[self.emp.pk, self.pattern.pk])
        )
        self.assertNotContains(resp, 'id="retroactive-confirm-modal"')

    def test_delete_modal_not_rendered_on_earliest(self):
        resp = self.client.get(
            reverse("pattern_edit", args=[self.emp.pk, self.pattern.pk])
        )
        self.assertNotContains(resp, 'id="delete-pattern-modal"')

    def test_delete_modal_rendered_on_non_earliest(self):
        later = ShiftPattern.objects.create(
            employee=self.emp,
            effective_from=_monday(timezone.localdate()) + timedelta(weeks=2),
            effective_to=None,
        )
        resp = self.client.get(reverse("pattern_edit", args=[self.emp.pk, later.pk]))
        self.assertContains(resp, 'id="delete-pattern-modal"')

    def test_edit_includes_save_pattern_modal(self):
        resp = self.client.get(
            reverse("pattern_edit", args=[self.emp.pk, self.pattern.pk])
        )
        self.assertContains(resp, 'id="confirm-save-pattern-modal"')

    def test_edit_cancel_uses_discard_modal(self):
        resp = self.client.get(
            reverse("pattern_edit", args=[self.emp.pk, self.pattern.pk])
        )
        self.assertContains(resp, "openConfirmDiscardModal(")


@override_settings(CACHES=_LOCMEM_CACHES)
class PatternEditPostTests(TestCase):
    def setUp(self):
        self.user = make_manager_user()
        self.client.force_login(self.user)
        self.emp = make_employee(with_pattern=True)
        self.pattern = self.emp.patterns.order_by("effective_from").first()
        # Push effective_from 4 weeks into the past so retroactive flows
        # exercise the guard.
        self.pattern.effective_from = _monday(timezone.localdate()) - timedelta(weeks=4)
        self.pattern.save(update_fields=["effective_from"])

    def _form_data(self, **overrides):
        data = {
            "cycle_weeks": "1",
            "week_0_day_0_start": "09:00",
            "week_0_day_0_end": "17:00",
            "retroactive_confirmed": "1",
        }
        data.update(overrides)
        return data

    def _post(self, **overrides):
        return self.client.post(
            reverse("pattern_edit", args=[self.emp.pk, self.pattern.pk]),
            self._form_data(**overrides),
        )

    def test_basic_save(self):
        resp = self._post()
        self.assertEqual(resp.status_code, 302)
        shift = Shift.objects.get(pattern=self.pattern, week_offset=0, day=0)
        self.assertEqual(shift.start_time.strftime("%H:%M"), "09:00")
        self.assertEqual(shift.end_time.strftime("%H:%M"), "17:00")

    def test_clearing_a_shift_deletes_it(self):
        Shift.objects.create(
            pattern=self.pattern,
            week_offset=0,
            day=0,
            start_time="09:00",
            end_time="17:00",
        )
        resp = self._post(week_0_day_0_start="", week_0_day_0_end="")
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(
            Shift.objects.filter(pattern=self.pattern, week_offset=0, day=0).exists()
        )

    def test_retroactive_guard_blocks_without_confirm(self):
        resp = self._post(retroactive_confirmed="")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["errors"])

    def test_cycle_grow_within_span(self):
        self.pattern.effective_to = self.pattern.effective_from + timedelta(weeks=2)
        self.pattern.save(update_fields=["effective_to"])
        resp = self._post(cycle_weeks="2")
        self.assertEqual(resp.status_code, 302)
        self.pattern.refresh_from_db()
        self.assertEqual(self.pattern.cycle_weeks, 2)

    def test_cycle_grow_beyond_span_rejected(self):
        self.pattern.effective_to = self.pattern.effective_from + timedelta(weeks=1)
        self.pattern.save(update_fields=["effective_to"])
        resp = self._post(cycle_weeks="2")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["errors"])
        self.pattern.refresh_from_db()
        self.assertEqual(self.pattern.cycle_weeks, 1)

    def test_effective_from_never_changes_via_post(self):
        original = self.pattern.effective_from
        self._post(effective_from="2020-01-06")
        self.pattern.refresh_from_db()
        self.assertEqual(self.pattern.effective_from, original)

    def test_open_ended_pattern_grows_freely(self):
        # No effective_to; cycle can grow past 1 week.
        self.pattern.effective_to = None
        self.pattern.save(update_fields=["effective_to"])
        resp = self._post(cycle_weeks="4")
        self.assertEqual(resp.status_code, 302)
        self.pattern.refresh_from_db()
        self.assertEqual(self.pattern.cycle_weeks, 4)

    def test_confirmed_retroactive_save_skips_modal_on_rerender(self):
        # Confirmed save + validation error: hidden input stays "1"
        # so the next Save doesn't re-open the modal.
        resp = self._post(
            week_0_day_0_start="bad",
            week_0_day_0_end="17:00",
            retroactive_confirmed="1",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["retroactive_confirmed"])

    def test_edit_preserves_valid_cells_on_error(self):
        # BUG-003: valid cells must survive a single bad cell.
        # Defaults have week_0_day_0 = 9-5 valid; add a second day
        # with an unparseable start.
        resp = self._post(
            week_0_day_1_start="garbage",
            week_0_day_1_end="17:00",
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        # Day 0 preserved (unique values).
        self.assertEqual(html.count('value="9:00 AM"'), 1)
        self.assertEqual(html.count('value="5:00 PM"'), 1)
        # Nothing was saved.
        self.assertFalse(Shift.objects.filter(pattern=self.pattern).exists())


@override_settings(CACHES=_LOCMEM_CACHES)
class TruncatedPatternEditTests(TestCase):
    """Session 8.5: editing a truncated pattern (cycle_weeks > span).

    A split can leave a pattern with cycle_weeks=4 but effective_to
    only 2 weeks out. Reducing the cycle must be allowed, and the
    edit prefill must use the pattern's own cycle offsets — not the
    next pattern's data — so an unchanged save doesn't silently
    overwrite hidden offsets.
    """

    def setUp(self):
        self.user = make_manager_user()
        self.client.force_login(self.user)
        self.emp = make_employee(start_date=settings.CYCLE_EPOCH, with_pattern=True)
        self.p = self.emp.patterns.order_by("effective_from").first()
        # Truncate to 2 weeks while keeping cycle_weeks=4. Anchor
        # effective_from at CYCLE_EPOCH so base_offset is deterministic.
        self.p.effective_from = settings.CYCLE_EPOCH
        self.p.effective_to = self.p.effective_from + timedelta(weeks=2)
        self.p.cycle_weeks = 4
        self.p.save(update_fields=["effective_from", "effective_to", "cycle_weeks"])
        # Distinct shifts at each of the 4 offsets so prefill tests
        # can verify which offset rendered in which panel.
        for off, hour in enumerate(["09", "10", "11", "12"]):
            Shift.objects.create(
                pattern=self.p,
                week_offset=off,
                day=0,
                start_time=f"{hour}:00",
                end_time=f"{int(hour) + 8}:00",
            )

    def _post(self, **overrides):
        data = {
            "cycle_weeks": "4",
            "week_0_day_0_start": "09:00",
            "week_0_day_0_end": "17:00",
            "week_1_day_0_start": "10:00",
            "week_1_day_0_end": "18:00",
            "week_2_day_0_start": "11:00",
            "week_2_day_0_end": "19:00",
            "week_3_day_0_start": "12:00",
            "week_3_day_0_end": "20:00",
            "retroactive_confirmed": "1",
        }
        data.update(overrides)
        return self.client.post(
            reverse("pattern_edit", args=[self.emp.pk, self.p.pk]), data
        )

    def test_prefill_uses_own_cycle_for_panels_beyond_span(self):
        resp = self.client.get(reverse("pattern_edit", args=[self.emp.pk, self.p.pk]))
        self.assertEqual(resp.status_code, 200)
        weeks = resp.context["weeks"]
        # base_offset=0 (eff_from == EPOCH). Panel N → offset N.
        self.assertEqual(
            weeks[2]["rows"][0]["shift"].start_time.strftime("%H:%M"),
            "11:00",
        )
        self.assertEqual(
            weeks[3]["rows"][0]["shift"].start_time.strftime("%H:%M"),
            "12:00",
        )

    def test_unchanged_cycle_save_allowed(self):
        resp = self._post(cycle_weeks="4")
        self.assertEqual(resp.status_code, 302)
        self.p.refresh_from_db()
        self.assertEqual(self.p.cycle_weeks, 4)
        # Offsets 2 and 3 preserved with their original values, not
        # overwritten with next-pattern data.
        self.assertEqual(
            Shift.objects.get(pattern=self.p, week_offset=2, day=0).start_time.strftime(
                "%H:%M"
            ),
            "11:00",
        )
        self.assertEqual(
            Shift.objects.get(pattern=self.p, week_offset=3, day=0).start_time.strftime(
                "%H:%M"
            ),
            "12:00",
        )

    def test_reduced_cycle_save_allowed(self):
        resp = self._post(
            cycle_weeks="2",
            week_2_day_0_start="",
            week_2_day_0_end="",
            week_3_day_0_start="",
            week_3_day_0_end="",
        )
        self.assertEqual(resp.status_code, 302)
        self.p.refresh_from_db()
        self.assertEqual(self.p.cycle_weeks, 2)
        self.assertFalse(
            Shift.objects.filter(pattern=self.p, week_offset__gte=2).exists()
        )

    def test_grow_beyond_current_cycle_still_rejected(self):
        # Pattern has cycle_weeks=4, span=2. Trying to grow is
        # impossible from 4 (max). Shrink to 3 first, then try 4.
        self.p.cycle_weeks = 3
        self.p.save(update_fields=["cycle_weeks"])
        resp = self._post(cycle_weeks="4")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["errors"])
