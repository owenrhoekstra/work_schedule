"""Coverage for the pattern edit page (Session 6)."""

from datetime import timedelta

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
        self.emp = make_employee()
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
            self.pattern.effective_from = _monday(timezone.localdate()) - timedelta(
                weeks=4
            )
            self.pattern.save(update_fields=["effective_from"])
            resp = self.client.get(
                reverse("pattern_edit", args=[self.emp.pk, self.pattern.pk])
            )
            self.assertContains(resp, "retroactive-confirm-modal")

        def test_retroactive_modal_not_rendered_on_future_pattern(self):
            future = _monday(timezone.localdate()) + timedelta(weeks=4)
            self.pattern.effective_from = future
            self.pattern.save(update_fields=["effective_from"])
            resp = self.client.get(
                reverse("pattern_edit", args=[self.emp.pk, self.pattern.pk])
            )
            self.assertNotContains(resp, "retroactive-confirm-modal")

        def test_delete_modal_not_rendered_on_earliest(self):
            resp = self.client.get(
                reverse("pattern_edit", args=[self.emp.pk, self.pattern.pk])
            )
            self.assertNotContains(resp, "delete-pattern-modal")

        def test_delete_modal_rendered_on_non_earliest(self):
            later = ShiftPattern.objects.create(
                employee=self.emp,
                effective_from=_monday(timezone.localdate()) + timedelta(weeks=2),
                effective_to=None,
            )
            resp = self.client.get(
                reverse("pattern_edit", args=[self.emp.pk, later.pk])
            )
            self.assertContains(resp, "delete-pattern-modal")

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


@override_settings(CACHES=_LOCMEM_CACHES)
class PatternEditPostTests(TestCase):
    def setUp(self):
        self.user = make_manager_user()
        self.client.force_login(self.user)
        self.emp = make_employee()
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
