"""Test factories for the accounts app.

Re-exports `make_staff_user` and `make_superuser` from the schedule
factories, which handle company-scoped memberships correctly.

Local `make_employee` override preserved for its distinct default
email ("emp@example.com") vs the schedule-side "test@example.com".

Branch A: role moved to EmployeeTeam.role (per-team TeamRole). No
`role=` kwarg on Employee.
"""

from django.utils import timezone

from schedule.models import Company, Employee
from schedule.tests.factories import (
    make_company,
    make_staff_user,  # noqa: F401  (re-export)
    make_superuser,  # noqa: F401  (re-export)
)


def make_employee(email="emp@example.com", **kwargs):
    """Create an Employee.

    Company defaults to the first existing company (matching the
    schedule-side factory) so test data lands in the same tenant by
    default. Pass `company=` to place an employee in a specific one.
    """
    company = kwargs.pop("company", None) or (
        Company.objects.order_by("id").first() or make_company()
    )
    return Employee.objects.create(
        first_name=kwargs.pop("first_name", "Test"),
        last_name=kwargs.pop("last_name", "User"),
        email=email,
        company=company,
        start_date=kwargs.pop("start_date", timezone.localdate()),
        **kwargs,
    )
