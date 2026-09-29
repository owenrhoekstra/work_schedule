from datetime import date, datetime, timedelta

from django.test import SimpleTestCase

from schedule.views import (
    _format_duration,
    _format_time_12,
    _ordinal,
    _parse_time,
    _week_start,
)


class ParseTimeTests(SimpleTestCase):
    def test_empty_returns_none(self):
        self.assertIsNone(_parse_time(""))
        self.assertIsNone(_parse_time(None))
        self.assertIsNone(_parse_time("   "))

    def test_24_hour(self):
        self.assertEqual(_parse_time("09:00"), datetime(1900, 1, 1, 9, 0).time())
        self.assertEqual(_parse_time("17:30"), datetime(1900, 1, 1, 17, 30).time())
        self.assertEqual(_parse_time("23:59"), datetime(1900, 1, 1, 23, 59).time())

    def test_24_hour_with_seconds(self):
        self.assertEqual(
            _parse_time("09:15:30"), datetime(1900, 1, 1, 9, 15, 30).time()
        )

    def test_compact_24_hour(self):
        self.assertEqual(_parse_time("0900"), datetime(1900, 1, 1, 9, 0).time())

    def test_12_hour_with_space(self):
        self.assertEqual(_parse_time("9:00 AM"), datetime(1900, 1, 1, 9, 0).time())
        self.assertEqual(_parse_time("5:30 PM"), datetime(1900, 1, 1, 17, 30).time())

    def test_12_hour_no_space(self):
        self.assertEqual(_parse_time("9:00AM"), datetime(1900, 1, 1, 9, 0).time())
        self.assertEqual(_parse_time("5:30PM"), datetime(1900, 1, 1, 17, 30).time())

    def test_12_hour_hour_only(self):
        self.assertEqual(_parse_time("9 AM"), datetime(1900, 1, 1, 9, 0).time())
        self.assertEqual(_parse_time("9AM"), datetime(1900, 1, 1, 9, 0).time())

    def test_lowercase_am_pm(self):
        self.assertEqual(_parse_time("9:00 am"), datetime(1900, 1, 1, 9, 0).time())
        self.assertEqual(_parse_time("5:30 pm"), datetime(1900, 1, 1, 17, 30).time())

    def test_dots_ignored(self):
        self.assertEqual(_parse_time("9.00 AM"), datetime(1900, 1, 1, 9, 0).time())

    def test_12_hour_midnight_and_noon(self):
        self.assertEqual(_parse_time("12:00 AM"), datetime(1900, 1, 1, 0, 0).time())
        self.assertEqual(_parse_time("12:00 PM"), datetime(1900, 1, 1, 12, 0).time())

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            _parse_time("not a time")
        with self.assertRaises(ValueError):
            _parse_time("25:00")
        with self.assertRaises(ValueError):
            _parse_time("13:00 PM")


class FormatTime12Tests(SimpleTestCase):
    def test_morning_no_leading_zero(self):
        self.assertEqual(_format_time_12(datetime(1900, 1, 1, 9, 0).time()), "9:00 AM")

    def test_morning_with_leading_zero_stripped(self):
        # Even though we format %I which gives "09", we strip the leading zero
        self.assertEqual(_format_time_12(datetime(1900, 1, 1, 9, 5).time()), "9:05 AM")

    def test_afternoon(self):
        self.assertEqual(
            _format_time_12(datetime(1900, 1, 1, 17, 30).time()), "5:30 PM"
        )

    def test_noon(self):
        self.assertEqual(
            _format_time_12(datetime(1900, 1, 1, 12, 0).time()), "12:00 PM"
        )

    def test_midnight(self):
        self.assertEqual(_format_time_12(datetime(1900, 1, 1, 0, 0).time()), "12:00 AM")


class FormatDurationTests(SimpleTestCase):
    def test_zero(self):
        self.assertEqual(_format_duration(timedelta()), "0h 00m")

    def test_whole_hours(self):
        self.assertEqual(_format_duration(timedelta(hours=8)), "8h 00m")

    def test_minutes_only(self):
        self.assertEqual(_format_duration(timedelta(minutes=30)), "0h 30m")

    def test_hours_and_minutes(self):
        self.assertEqual(_format_duration(timedelta(hours=7, minutes=45)), "7h 45m")

    def test_minutes_padded(self):
        self.assertEqual(_format_duration(timedelta(hours=8, minutes=5)), "8h 05m")

    def test_seconds_truncated(self):
        self.assertEqual(_format_duration(timedelta(hours=1, seconds=59)), "1h 00m")


class OrdinalTests(SimpleTestCase):
    def test_ones(self):
        self.assertEqual(_ordinal(1), "1st")
        self.assertEqual(_ordinal(2), "2nd")
        self.assertEqual(_ordinal(3), "3rd")
        self.assertEqual(_ordinal(4), "4th")

    def test_teens(self):
        self.assertEqual(_ordinal(11), "11th")
        self.assertEqual(_ordinal(12), "12th")
        self.assertEqual(_ordinal(13), "13th")
        self.assertEqual(_ordinal(14), "14th")

    def test_twenties(self):
        self.assertEqual(_ordinal(21), "21st")
        self.assertEqual(_ordinal(22), "22nd")
        self.assertEqual(_ordinal(23), "23rd")
        self.assertEqual(_ordinal(24), "24th")

    def test_hundreds(self):
        self.assertEqual(_ordinal(100), "100th")
        self.assertEqual(_ordinal(101), "101st")
        self.assertEqual(_ordinal(111), "111th")


class WeekStartTests(SimpleTestCase):
    def test_monday_returns_itself(self):
        # 2026-01-05 is a Monday
        self.assertEqual(_week_start(date(2026, 1, 5)), date(2026, 1, 5))

    def test_midweek_returns_previous_monday(self):
        self.assertEqual(_week_start(date(2026, 1, 7)), date(2026, 1, 5))  # Wed
        self.assertEqual(_week_start(date(2026, 1, 9)), date(2026, 1, 5))  # Fri

    def test_saturday_returns_previous_monday(self):
        self.assertEqual(_week_start(date(2026, 1, 10)), date(2026, 1, 5))

    def test_sunday_returns_previous_monday(self):
        # Sunday is day 6 of the ISO week; Monday-start week puts it in the prior week
        self.assertEqual(_week_start(date(2026, 1, 11)), date(2026, 1, 5))
