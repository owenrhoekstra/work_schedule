"""Test factories for the accounts app.

Branch 2 post-review: `make_superuser` and `make_staff_user` re-export
from schedule.tests.factories, which handle company-scoped memberships
correctly (accepting `company=` and creating an active
CompanyMembership).

`make_employee` mirrors the schedule-side factory's company default
(Company.objects.first() or make_company()) so tests that create a
user and an employee in the same test share one company by default —
critical for approve_account, which resolves the pending membership at
request.company and would otherwise silently reject when the two users
are at different companies.

Local `make_employee` override preserved for its distinct default
email ("emp@example.com") vs the schedule-side "test@example.com".
"""

from django.utils import timezone

from schedule.models import Company, Employee
from schedule.tests.factories import (
    make_company,
    make_role,
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
    role = kwargs.pop("role", None) or make_role(company=company)
    return Employee.objects.create(
        first_name=kwargs.pop("first_name", "Test"),
        last_name=kwargs.pop("last_name", "User"),
        email=email,
        role=role,
        company=company,
        start_date=kwargs.pop("start_date", timezone.localdate()),
        **kwargs,
    )
