from datetime import timedelta

from django.conf import settings
from django.test import TestCase, override_settings

from schedule.views import _week_offset_for

from .factories import make_employee

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


@override_settings(CACHES=_LOCMEM_CACHES)
class WeekOffsetTests(TestCase):
    def test_single_week_always_zero(self):
        emp = make_employee(cycle_weeks=1)
        epoch = settings.CYCLE_EPOCH
        self.assertEqual(_week_offset_for(epoch, emp), 0)
        self.assertEqual(_week_offset_for(epoch + timedelta(weeks=1), emp), 0)
        self.assertEqual(_week_offset_for(epoch + timedelta(weeks=52), emp), 0)

    def test_two_week_alternates(self):
        emp = make_employee(cycle_weeks=2)
        epoch = settings.CYCLE_EPOCH
        self.assertEqual(_week_offset_for(epoch, emp), 0)
        self.assertEqual(_week_offset_for(epoch + timedelta(weeks=1), emp), 1)
        self.assertEqual(_week_offset_for(epoch + timedelta(weeks=2), emp), 0)
        self.assertEqual(_week_offset_for(epoch + timedelta(weeks=3), emp), 1)

    def test_three_week_cycles(self):
        emp = make_employee(cycle_weeks=3)
        epoch = settings.CYCLE_EPOCH
        self.assertEqual(_week_offset_for(epoch, emp), 0)
        self.assertEqual(_week_offset_for(epoch + timedelta(weeks=1), emp), 1)
        self.assertEqual(_week_offset_for(epoch + timedelta(weeks=2), emp), 2)
        self.assertEqual(_week_offset_for(epoch + timedelta(weeks=3), emp), 0)

    def test_four_week_cycles(self):
        emp = make_employee(cycle_weeks=4)
        epoch = settings.CYCLE_EPOCH
        for i in range(4):
            self.assertEqual(_week_offset_for(epoch + timedelta(weeks=i), emp), i)
        self.assertEqual(_week_offset_for(epoch + timedelta(weeks=4), emp), 0)

    def test_weeks_before_epoch_wrap_correctly(self):
        """Python modulo gives a positive result for negative dividends."""
        emp = make_employee(cycle_weeks=3)
        epoch = settings.CYCLE_EPOCH
        # Two weeks before epoch = offset (3 - 2) = 1
        self.assertEqual(_week_offset_for(epoch - timedelta(weeks=2), emp), 1)
        self.assertEqual(_week_offset_for(epoch - timedelta(weeks=1), emp), 2)
