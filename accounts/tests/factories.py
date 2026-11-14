"""Test factories for the accounts app.

Branch 1: employee creation routes through
`schedule.tests.factories` so the multi-tenancy `company=` requirement
is handled in one place. No module-level state — each call defaults to
a fresh Company unless `company=` is passed.
"""

from datetime import date

from django.contrib.auth.models import User

from schedule.models import Employee
from schedule.tests.factories import make_company, make_role


def make_employee(email="emp@example.com", **kwargs):
    """Create an Employee with a company and role.

    `company` defaults to a fresh one; pass `company=` to share a
    company with another employee. `role` defaults to a fresh
    company-scoped "Staff" role for the resolved company.
    """
    company = kwargs.pop("company", None) or make_company()
    role = kwargs.pop("role", None) or make_role(company=company)
    return Employee.objects.create(
        first_name=kwargs.pop("first_name", "Test"),
        last_name=kwargs.pop("last_name", "User"),
        email=email,
        role=role,
        company=company,
        start_date=kwargs.pop("start_date", date.today()),
        **kwargs,
    )


def make_superuser(username="admin"):
    return User.objects.create_superuser(
        username=username, password="pass", email=f"{username}@example.com"
    )


def make_staff_user(username="staff"):
    return User.objects.create_user(
        username=username, password="pass", email=f"{username}@example.com"
    )
