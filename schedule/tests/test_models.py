from datetime import date, timedelta

from django.db import IntegrityError
from django.test import TestCase

from schedule.models import (
    Employee,
    EmploymentPeriod,
    Role,
    Shift,
    ShiftOverride,
    Title,
)

from .factories import make_employee, make_role, make_title


class EmployeeStrTests(TestCase):
    def test_with_title_shown(self):
        title = make_title("Dr.")
        emp = make_employee(title=title, first_name="Jane", last_name="Doe")
        self.assertEqual(str(emp), "Dr. Jane Doe")

    def test_with_title_hidden(self):
        title = Title.objects.create(name="Prof.", show_in_name=False)
        emp = make_employee(title=title, first_name="Jane", last_name="Doe")
        self.assertEqual(str(emp), "Jane Doe")

    def test_without_title(self):
        emp = make_employee(first_name="Jane", last_name="Doe")
        self.assertEqual(str(emp), "Jane Doe")


class UniqueConstraintsTests(TestCase):
    def test_two_active_employees_cannot_share_email(self):
        make_employee(email="x@example.com")
        with self.assertRaises(IntegrityError):
            make_employee(email="x@example.com")

    def test_inactive_employee_can_share_email_with_active(self):
        first = make_employee(email="x@example.com")
        first.is_active = False
        first.save()
        # Should succeed
        make_employee(email="x@example.com")

    def test_shift_unique_per_week_offset_and_day(self):
        emp = make_employee()
        Shift.objects.create(
            employee=emp,
            week_offset=0,
            day=0,
            start_time="09:00",
            end_time="17:00",
        )
        with self.assertRaises(IntegrityError):
            Shift.objects.create(
                employee=emp,
                week_offset=0,
                day=0,
                start_time="10:00",
                end_time="18:00",
            )

    def test_shift_override_unique_per_date(self):
        emp = make_employee()
        d = date.today()
        ShiftOverride.objects.create(employee=emp, date=d, is_off=True)
        with self.assertRaises(IntegrityError):
            ShiftOverride.objects.create(employee=emp, date=d, is_off=False)


class OrderingTests(TestCase):
    def test_roles_ordered_by_display_then_name(self):
        Role.objects.create(name="B", display_order=20)
        Role.objects.create(name="A", display_order=10)
        Role.objects.create(name="C", display_order=10)
        names = list(Role.objects.values_list("name", flat=True))
        self.assertEqual(names, ["A", "C", "B"])

    def test_titles_ordered_by_display_then_name(self):
        Title.objects.create(name="Z", display_order=10)
        Title.objects.create(name="A", display_order=10)
        Title.objects.create(name="M", display_order=5)
        names = list(Title.objects.values_list("name", flat=True))
        self.assertEqual(names, ["M", "A", "Z"])


class EmploymentPeriodTests(TestCase):
    def test_str_open_period(self):
        emp = make_employee()
        period = emp.periods.first()
        self.assertIn("present", str(period))

    def test_str_closed_period(self):
        emp = make_employee()
        period = emp.periods.first()
        period.end_date = date(2026, 6, 30)
        period.save()
        self.assertIn("2026-06-30", str(period))


class DayOverrideTests(TestCase):
    def test_str(self):
        from schedule.models import DayOverride

        d = DayOverride.objects.create(date=date(2026, 12, 25), status="holiday")
        self.assertIn("Holiday", str(d))
