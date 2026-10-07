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
    def _pattern(self, cycle_weeks):
        emp = make_employee(cycle_weeks=cycle_weeks)
        return emp.patterns.first()

    def test_single_week_always_zero(self):
        pattern = self._pattern(1)
        epoch = settings.CYCLE_EPOCH
        self.assertEqual(_week_offset_for(epoch, pattern), 0)
        self.assertEqual(_week_offset_for(epoch + timedelta(weeks=1), pattern), 0)
        self.assertEqual(_week_offset_for(epoch + timedelta(weeks=52), pattern), 0)

    def test_two_week_alternates(self):
        pattern = self._pattern(2)
        epoch = settings.CYCLE_EPOCH
        self.assertEqual(_week_offset_for(epoch, pattern), 0)
        self.assertEqual(_week_offset_for(epoch + timedelta(weeks=1), pattern), 1)
        self.assertEqual(_week_offset_for(epoch + timedelta(weeks=2), pattern), 0)
        self.assertEqual(_week_offset_for(epoch + timedelta(weeks=3), pattern), 1)

    def test_three_week_cycles(self):
        pattern = self._pattern(3)
        epoch = settings.CYCLE_EPOCH
        self.assertEqual(_week_offset_for(epoch, pattern), 0)
        self.assertEqual(_week_offset_for(epoch + timedelta(weeks=1), pattern), 1)
        self.assertEqual(_week_offset_for(epoch + timedelta(weeks=2), pattern), 2)
        self.assertEqual(_week_offset_for(epoch + timedelta(weeks=3), pattern), 0)

    def test_four_week_cycles(self):
        pattern = self._pattern(4)
        epoch = settings.CYCLE_EPOCH
        for i in range(4):
            self.assertEqual(_week_offset_for(epoch + timedelta(weeks=i), pattern), i)
        self.assertEqual(_week_offset_for(epoch + timedelta(weeks=4), pattern), 0)

    def test_weeks_before_epoch_wrap_correctly(self):
        pattern = self._pattern(3)
        epoch = settings.CYCLE_EPOCH
        self.assertEqual(_week_offset_for(epoch - timedelta(weeks=2), pattern), 1)
        self.assertEqual(_week_offset_for(epoch - timedelta(weeks=1), pattern), 2)
