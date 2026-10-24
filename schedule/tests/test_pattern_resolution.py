from datetime import date

from django.test import TestCase, override_settings

from schedule.models import ShiftPattern
from schedule.views import _pattern_for_week

from .factories import make_employee

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


@override_settings(CACHES=_LOCMEM_CACHES)
class PatternForWeekTests(TestCase):
    """Direct coverage for _pattern_for_week.

    The factory creates an initial open-ended pattern via the
    post_save signal. Each test clears it so the scenario is explicit.
    """

    def setUp(self):
        self.emp = make_employee()
        self.emp.patterns.all().delete()

    def _make(self, effective_from, effective_to=None):
        return ShiftPattern.objects.create(
            employee=self.emp,
            effective_from=effective_from,
            effective_to=effective_to,
            cycle_weeks=1,
        )

    def test_no_patterns_returns_none(self):
        self.assertIsNone(_pattern_for_week(self.emp, date(2026, 1, 5)))

    def test_open_pattern_covers_week_at_start(self):
        p = self._make(date(2026, 1, 5))
        self.assertEqual(_pattern_for_week(self.emp, date(2026, 1, 5)), p)

    def test_open_pattern_covers_far_future_week(self):
        p = self._make(date(2026, 1, 5))
        self.assertEqual(_pattern_for_week(self.emp, date(2027, 6, 1)), p)

    def test_open_pattern_does_not_cover_week_before_start(self):
        self._make(date(2026, 1, 5))
        self.assertIsNone(_pattern_for_week(self.emp, date(2025, 12, 29)))

    def test_closed_pattern_covers_week_inside_range(self):
        p = self._make(date(2026, 1, 5), date(2026, 2, 2))
        self.assertEqual(_pattern_for_week(self.emp, date(2026, 1, 19)), p)

    def test_closed_pattern_does_not_cover_week_at_effective_to(self):
        self._make(date(2026, 1, 5), date(2026, 2, 2))
        # effective_to is exclusive; the week starting on it should not match
        self.assertIsNone(_pattern_for_week(self.emp, date(2026, 2, 2)))

    def test_adjacent_boundary_goes_to_successor(self):
        self._make(date(2026, 1, 5), date(2026, 2, 2))
        b = self._make(date(2026, 2, 2))
        self.assertEqual(_pattern_for_week(self.emp, date(2026, 2, 2)), b)

    def test_adjacent_week_within_first(self):
        a = self._make(date(2026, 1, 5), date(2026, 2, 2))
        self._make(date(2026, 2, 2))
        self.assertEqual(_pattern_for_week(self.emp, date(2026, 1, 26)), a)

    def test_adjacent_week_within_second(self):
        self._make(date(2026, 1, 5), date(2026, 2, 2))
        b = self._make(date(2026, 2, 2))
        self.assertEqual(_pattern_for_week(self.emp, date(2026, 2, 9)), b)

    def test_legacy_overlap_max_effective_from_wins(self):
        # Legacy overlap: shouldn't exist after the form rewrite, but
        # the transition period must not regress the old "latest wins"
        # behavior for patterns that already overlap.
        self._make(date(2026, 1, 5), date(2026, 3, 2))
        y = self._make(date(2026, 2, 2), date(2026, 3, 2))
        self.assertEqual(_pattern_for_week(self.emp, date(2026, 2, 9)), y)