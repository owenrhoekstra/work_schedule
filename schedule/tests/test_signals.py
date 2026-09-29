from datetime import date, timedelta

from django.test import TestCase

from schedule.models import EmploymentPeriod

from .factories import make_employee, make_staff_user


class EmploymentPeriodSignalTests(TestCase):
    def test_creating_employee_creates_period(self):
        emp = make_employee(start_date=date(2026, 1, 1))
        self.assertEqual(emp.periods.count(), 1)
        period = emp.periods.first()
        self.assertEqual(period.start_date, date(2026, 1, 1))
        self.assertIsNone(period.end_date)

    def test_employee_with_last_day_on_create_gets_closed_period(self):
        emp = make_employee(
            start_date=date(2026, 1, 1),
            last_day=date(2026, 3, 31),
        )
        period = emp.periods.first()
        self.assertEqual(period.end_date, date(2026, 4, 1))

    def test_existing_employee_update_does_not_create_second_period(self):
        emp = make_employee()
        self.assertEqual(emp.periods.count(), 1)
        emp.first_name = "Changed"
        emp.save()
        self.assertEqual(emp.periods.count(), 1)

    def test_manually_created_period_is_not_duplicated_on_save(self):
        emp = make_employee()
        # Simulate a second period being added by reactivation
        EmploymentPeriod.objects.create(
            employee=emp, start_date=date(2030, 1, 1), end_date=None
        )
        emp.save()
        self.assertEqual(emp.periods.count(), 2)


class UserSyncSignalTests(TestCase):
    def test_name_change_mirrors_to_user(self):
        user = make_staff_user()
        emp = make_employee(email=user.email)
        emp.user = user
        emp.save()
        emp.first_name = "Changed"
        emp.last_name = "New"
        emp.save()
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Changed")
        self.assertEqual(user.last_name, "New")

    def test_email_change_mirrors_to_user(self):
        user = make_staff_user()
        emp = make_employee(email=user.email)
        emp.user = user
        emp.save()
        emp.email = "newemail@example.com"
        emp.save()
        user.refresh_from_db()
        self.assertEqual(user.email, "newemail@example.com")

    def test_employee_without_user_does_not_error(self):
        emp = make_employee()
        emp.first_name = "Changed"
        emp.save()  # Should not raise
        self.assertEqual(emp.user_id, None)
