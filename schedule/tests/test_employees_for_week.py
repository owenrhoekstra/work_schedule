from datetime import date, timedelta

from django.test import TestCase, override_settings

from schedule.models import EmploymentPeriod
from schedule.views import _employees_for_week

from .factories import make_employee

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}

# Known Mondays so `_employees_for_week` gets clean week boundaries.
MON_JUL = date(2025, 7, 7)  # week containing the start of P1
MON_SEP_GAP = date(2025, 10, 6)  # week inside the gap between P1 and P2
MON_NOV = date(2025, 11, 10)  # week containing the start of P2
MON_PRE = date(2025, 6, 2)  # week before any period


@override_settings(CACHES=_LOCMEM_CACHES)
class EmployeesForWeekPeriodOverlapTests(TestCase):
    """Regression: chained .filter() on periods created separate JOINs,
    so an employee with two non-overlapping periods appeared in the gap
    between them (each half of the overlap test was satisfied by a
    different period row). The fix merges the conditions into one Q so
    both halves apply to the same joined row.
    """

    def setUp(self):
        self.emp = make_employee(
            email="rehire@example.com",
            start_date=date(2025, 7, 6),
        )
        # The post_save signal created an initial open period. Replace it
        # with the two-period scenario we want to test.
        self.emp.periods.all().delete()
        EmploymentPeriod.objects.create(
            employee=self.emp,
            start_date=date(2025, 7, 6),
            end_date=date(2025, 9, 7),  # exclusive
        )
        EmploymentPeriod.objects.create(
            employee=self.emp,
            start_date=date(2025, 11, 6),
            end_date=None,
        )

    def _ids(self, week_start):
        return set(_employees_for_week(week_start).values_list("pk", flat=True))

    # ----- present when the week overlaps a real period -----

    def test_present_in_first_period_week(self):
        self.assertIn(self.emp.pk, self._ids(MON_JUL))

    def test_present_in_second_period_week(self):
        self.assertIn(self.emp.pk, self._ids(MON_NOV))

    # ----- absent when no single period covers the week -----

    def test_absent_in_gap_between_periods(self):
        """The bug: old code returned the employee here because P1 matched
        the start_date half and P2 matched the end_date half across two
        separate joins."""
        self.assertNotIn(self.emp.pk, self._ids(MON_SEP_GAP))

    def test_absent_before_any_period(self):
        self.assertNotIn(self.emp.pk, self._ids(MON_PRE))

    # ----- boundary: end_date is exclusive -----

    def test_absent_on_week_starting_at_end_date(self):
        """P1 ends 2025-09-07, so the week of 2025-09-08 must not match."""
        # 2025-09-08 is a Monday
        self.assertNotIn(self.emp.pk, self._ids(date(2025, 9, 8)))

    def test_present_on_week_straddling_end_date(self):
        """Week of 2025-09-01 includes Sep 1–6, all inside P1."""
        # 2025-09-01 is a Monday
        self.assertIn(self.emp.pk, self._ids(date(2025, 9, 1)))

    # ----- single-period sanity check -----

    def test_single_open_period_still_works(self):
        self.emp.periods.all().delete()
        EmploymentPeriod.objects.create(
            employee=self.emp,
            start_date=date(2025, 7, 6),
            end_date=None,
        )
        self.assertIn(self.emp.pk, self._ids(MON_JUL))
        self.assertIn(self.emp.pk, self._ids(MON_SEP_GAP))
        self.assertIn(self.emp.pk, self._ids(MON_NOV))

    def test_reverse_order_periods(self):
        """Closed period first, open period later — same result as the
        other ordering, since the fix doesn't depend on row order."""
        self.emp.periods.all().delete()
        EmploymentPeriod.objects.create(
            employee=self.emp,
            start_date=date(2025, 7, 6),
            end_date=date(2025, 9, 7),
        )
        EmploymentPeriod.objects.create(
            employee=self.emp,
            start_date=date(2025, 11, 6),
            end_date=None,
        )
        # Same assertions as setUp ordering
        self.assertIn(self.emp.pk, self._ids(MON_JUL))
        self.assertNotIn(self.emp.pk, self._ids(MON_SEP_GAP))
        self.assertIn(self.emp.pk, self._ids(MON_NOV))
