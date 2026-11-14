"""Test factories for the schedule app.

Each helper is deliberately simple — no faker, no randomness, no
per-test uniqueness beyond what the tests ask for. When a test needs a
specific attribute, it passes it in; otherwise the defaults here are
the boring middle of the road.

Session 8: make_employee no longer creates a ShiftPattern
automatically (the app no longer does either). Tests opt in with
with_pattern=True or cycle_weeks=N.

Branch 1: make_employee auto-creates a fresh Company per call unless
`company=` is passed. Existing single-employee tests keep working;
tests that need two employees in the same company pass `company=`
explicitly. Role/Title creates are company-scoped for the same reason.
"""

import uuid  # add at top of file, above `from datetime import`
from datetime import date, timedelta

from django.contrib.auth.models import Group, Permission, User

from schedule.models import Company, Employee, Role, ShiftPattern, Title


def make_company(name="Test Company", slug=None):
    """Create a Company. Slug is unique per call unless explicitly given."""
    if slug is None:
        slug = f"test-company-{uuid.uuid4().hex[:8]}"
    return Company.objects.create(
        name=name,
        slug=slug,
        site_url="https://test.example.com",
        app_name=name,
        cycle_epoch=date(2026, 1, 5),
    )


def make_role(name="Staff", order=10, company=None, team=None):
    """Return a Role, creating it if needed.

    Company defaults to the first existing company (so all test data in
    one test lands in the same tenant) or a fresh one if none exists.
    """
    company = company or Company.objects.first() or make_company()
    role, _ = Role.objects.get_or_create(
        name=name,
        company=company,
        team=team,
        defaults={"display_order": order},
    )
    return role


def make_title(name="Dr.", company=None, team=None):
    """Return a Title, creating it if needed."""
    company = company or Company.objects.first() or make_company()
    title, _ = Title.objects.get_or_create(name=name, company=company, team=team)
    return title


def make_employee(
    email="test@example.com",
    role=None,
    company=None,
    start_date=None,
    with_pattern=False,
    **kwargs,
):
    """Create an Employee, optionally with an empty starting ShiftPattern.

    `company` defaults to the first existing company (so all employees
    created in one test share a tenant, matching `_current_company()`)
    or a fresh one if none exists. Pass `company=` explicitly to place
    an employee in a specific company.

    Post-Session 8, Employee creation does not auto-create a pattern.
    Opt in with `with_pattern=True` or `cycle_weeks=N`.
    """
    cycle_weeks = kwargs.pop("cycle_weeks", None)
    if cycle_weeks is not None:
        with_pattern = True
    if cycle_weeks is None:
        cycle_weeks = 1

    company = company or Company.objects.first() or make_company()
    role = role or make_role(company=company)
    employee = Employee.objects.create(
        first_name=kwargs.pop("first_name", "Test"),
        last_name=kwargs.pop("last_name", "User"),
        email=email,
        role=role,
        company=company,
        start_date=start_date or date.today(),
        **kwargs,
    )

    if with_pattern:
        anchor = employee.start_date - timedelta(days=employee.start_date.weekday())
        ShiftPattern.objects.create(
            employee=employee,
            effective_from=anchor,
            cycle_weeks=cycle_weeks,
        )

    return employee


def make_superuser(username="admin"):
    """Create a superuser with a known password ("pass")."""
    return User.objects.create_superuser(
        username=username, password="pass", email=f"{username}@example.com"
    )


def make_staff_user(username="staff"):
    """A user with only schedule.view_shift — the minimum to view the schedule."""
    user = User.objects.create_user(
        username=username, password="pass", email=f"{username}@example.com"
    )
    user.user_permissions.add(Permission.objects.get(codename="view_shift"))
    return user


def make_manager_user(username="manager"):
    """A user with every schedule permission but no superuser flag.

    Grants all current schedule permissions via queryset, so new
    permissions added to the app are automatically granted here.
    This matters post-SEC-006: `settings_*` views are gated on both
    `management_required` AND `permission_required("schedule.X")`,
    so "manager" users need the underlying perms too.

    Note: `management_required` checks group membership by name
    ("Management"), not permissions. Tests that need to hit management
    views must additionally add this user to a Management group — see
    `make_management_user` below.

    Branch 1: unchanged. Branch 2 migrates "is management" to a
    CompanyMembership(role="admin", status="active") check; this
    factory will then accept `company=` and create the membership.
    """
    user = User.objects.create_user(
        username=username, password="pass", email=f"{username}@example.com"
    )
    user.user_permissions.set(
        Permission.objects.filter(content_type__app_label="schedule")
    )
    return user


def make_management_user(username="management"):
    """A user with every schedule permission AND Management group membership.

    Required shape for views gated on both `management_required` and
    `permission_required` (SEC-006). Most write views and all settings
    views now require this combination. `make_manager_user` alone is
    insufficient — it grants the perms but not the Management group.

    Branch 1: unchanged. Branch 2 will add a CompanyMembership.
    """

    user = make_manager_user(username)
    mgmt, _ = Group.objects.get_or_create(name="Management")
    user.groups.add(mgmt)
    return user


def next_monday(today=None):
    """The Monday of next week, relative to `today` (defaults to today)."""
    today = today or date.today()
    return today + timedelta(days=7 - today.weekday())
