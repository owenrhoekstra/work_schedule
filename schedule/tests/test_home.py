from datetime import date, timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from schedule.models import DayOverride, Shift, ShiftOverride

from .factories import (
    make_employee,
    make_manager_user,
    make_role,
    make_staff_user,
)

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


@override_settings(CACHES=_LOCMEM_CACHES)
class HomePermissionTests(TestCase):
    def test_anonymous_redirected(self):
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)

    def test_staff_can_view(self):
        self.client.force_login(make_staff_user())
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)

    def test_user_without_view_shift_gets_403(self):
        from django.contrib.auth.models import User

        user = User.objects.create_user(username="nope", password="p")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("home")).status_code, 403)


@override_settings(CACHES=_LOCMEM_CACHES)
class HomeWeekNavigationTests(TestCase):
    def setUp(self):
        self.user = make_staff_user()
        self.client.force_login(self.user)

    def test_default_week_is_current(self):
        resp = self.client.get(reverse("home"))
        self.assertTrue(resp.context["is_current_week"])

    def test_week_param_parsed(self):
        resp = self.client.get(reverse("home"), {"week": "2026-01-07"})
        self.assertEqual(resp.context["week_start"], date(2026, 1, 5))

    def test_invalid_week_param_falls_back_to_current(self):
        resp = self.client.get(reverse("home"), {"week": "nonsense"})
        self.assertTrue(resp.context["is_current_week"])

    def test_prev_next_links_are_seven_days_apart(self):
        resp = self.client.get(reverse("home"), {"week": "2026-06-01"})
        self.assertEqual(
            resp.context["next_week"] - resp.context["prev_week"],
            timedelta(days=14),
        )

    def test_week_title_includes_ordinal(self):
        resp = self.client.get(reverse("home"), {"week": "2026-01-05"})
        self.assertEqual(resp.context["week_title"], "Week of January 5th")

    def test_week_title_includes_year_when_different(self):
        # Force current week to be in a different year
        with override_settings():  # no change needed
            pass
        resp = self.client.get(reverse("home"), {"week": "2020-01-06"})
        self.assertIn("2020", resp.context["week_title"])


@override_settings(CACHES=_LOCMEM_CACHES)
class HomeScheduleRenderingTests(TestCase):
    def setUp(self):
        self.user = make_superuser_quiet()
        self.client.force_login(self.user)
        self.role_a = make_role("Manager", order=10)
        self.role_b = make_role("Receptionist", order=20)
        self.mon = date.today() - timedelta(days=date.today().weekday())

    def test_employees_sorted_by_role_order_then_start(self):
        old_recep = make_employee(
            email="old@x.com", role=self.role_b, start_date=date(2020, 1, 1)
        )
        new_recep = make_employee(
            email="new@x.com", role=self.role_b, start_date=date(2024, 1, 1)
        )
        mgr = make_employee(email="m@x.com", role=self.role_a)

        resp = self.client.get(reverse("home"), {"week": self.mon.isoformat()})
        employees = [row["employee"] for row in resp.context["rows"]]
        self.assertEqual(employees, [mgr, old_recep, new_recep])

    def test_employee_not_yet_started_shows_dash(self):
        emp = make_employee(start_date=self.mon + timedelta(days=3))
        resp = self.client.get(reverse("home"), {"week": self.mon.isoformat()})
        row = resp.context["rows"][0]
        # Mon Tue Wed are dashes, Thu Fri Sat are their shifts (none here)
        for cell in row["cells"][:3]:
            self.assertEqual(cell["display"], "—")
            self.assertFalse(cell["is_employed"])

    def test_employee_deactivated_midweek_shows_gap(self):
        emp = make_employee(start_date=self.mon - timedelta(days=30))
        emp.last_day = self.mon + timedelta(days=1)  # Tue is last day
        emp.save()
        # Close period to reflect it
        period = emp.periods.first()
        period.end_date = self.mon + timedelta(days=2)  # Wed is first off day
        period.save()

        Shift.objects.create(
            employee=emp,
            week_offset=0,
            day=0,
            start_time="09:00",
            end_time="17:00",
        )
        resp = self.client.get(reverse("home"), {"week": self.mon.isoformat()})
        row = resp.context["rows"][0]
        self.assertTrue(row["cells"][0]["is_employed"])  # Mon
        self.assertTrue(row["cells"][1]["is_employed"])  # Tue
        self.assertFalse(row["cells"][2]["is_employed"])  # Wed
        self.assertEqual(row["cells"][2]["display"], "—")

    def test_day_override_shows_status(self):
        emp = make_employee()
        DayOverride.objects.create(date=self.mon, status="holiday")
        resp = self.client.get(reverse("home"), {"week": self.mon.isoformat()})
        row = resp.context["rows"][0]
        self.assertEqual(row["cells"][0]["display"], "Holiday")

    def test_day_override_ignores_employee_override(self):
        emp = make_employee()
        DayOverride.objects.create(date=self.mon, status="closed")
        ShiftOverride.objects.create(
            employee=emp,
            date=self.mon,
            start_time="10:00",
            end_time="14:00",
        )
        resp = self.client.get(reverse("home"), {"week": self.mon.isoformat()})
        row = resp.context["rows"][0]
        self.assertEqual(row["cells"][0]["display"], "Closed")

    def test_employee_override_shows_times(self):
        emp = make_employee()
        Shift.objects.create(
            employee=emp,
            week_offset=0,
            day=0,
            start_time="09:00",
            end_time="17:00",
        )
        ShiftOverride.objects.create(
            employee=emp,
            date=self.mon,
            start_time="10:00",
            end_time="14:00",
        )
        resp = self.client.get(reverse("home"), {"week": self.mon.isoformat()})
        row = resp.context["rows"][0]
        self.assertEqual(row["cells"][0]["display"], "10:00 AM - 2:00 PM")
        self.assertTrue(row["cells"][0]["has_override"])
        self.assertEqual(row["cells"][0]["state_class"], "text-brand-coral")

    def test_off_override_shows_off(self):
        emp = make_employee()
        Shift.objects.create(
            employee=emp,
            week_offset=0,
            day=0,
            start_time="09:00",
            end_time="17:00",
        )
        ShiftOverride.objects.create(employee=emp, date=self.mon, is_off=True)
        resp = self.client.get(reverse("home"), {"week": self.mon.isoformat()})
        row = resp.context["rows"][0]
        self.assertEqual(row["cells"][0]["display"], "OFF")
        self.assertEqual(row["cells"][0]["state_class"], "text-brand-coral")

    def test_total_hours_sums_defaults(self):
        emp = make_employee()
        for day in range(3):  # Mon, Tue, Wed
            Shift.objects.create(
                employee=emp,
                week_offset=0,
                day=day,
                start_time="09:00",
                end_time="17:00",
            )
        resp = self.client.get(reverse("home"), {"week": self.mon.isoformat()})
        row = resp.context["rows"][0]
        self.assertEqual(row["total_hours"], "24h 00m")

    def test_cycle_label_shown_for_multicycle(self):
        emp = make_employee(cycle_weeks=2)
        resp = self.client.get(reverse("home"), {"week": self.mon.isoformat()})
        row = resp.context["rows"][0]
        self.assertIsNotNone(row["cycle_label"])

    def test_cycle_label_none_for_single_week(self):
        emp = make_employee(cycle_weeks=1)
        resp = self.client.get(reverse("home"), {"week": self.mon.isoformat()})
        row = resp.context["rows"][0]
        self.assertIsNone(row["cycle_label"])

    def test_last_day_shown_for_management(self):
        emp = make_employee()
        emp.last_day = self.mon + timedelta(days=10)
        emp.save()
        resp = self.client.get(reverse("home"), {"week": self.mon.isoformat()})
        row = resp.context["rows"][0]
        self.assertEqual(row["last_day"], emp.last_day)

    def test_employees_filtered_out_before_start(self):
        # Employee starts 3 weeks from now — doesn't appear in this week
        far_future = self.mon + timedelta(days=21)
        make_employee(start_date=far_future)
        resp = self.client.get(reverse("home"), {"week": self.mon.isoformat()})
        self.assertEqual(len(resp.context["rows"]), 0)

    def test_employees_filtered_out_after_last_day(self):
        emp = make_employee(start_date=self.mon - timedelta(days=30))
        period = emp.periods.first()
        period.end_date = self.mon  # ended before this week
        period.save()
        resp = self.client.get(reverse("home"), {"week": self.mon.isoformat()})
        self.assertEqual(len(resp.context["rows"]), 0)


def make_superuser_quiet():
    """Superuser helper without the make_superuser name clash."""
    from .factories import make_superuser

    return make_superuser()
