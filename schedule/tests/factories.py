"""Test factories for the schedule app.

Each helper is deliberately simple — no faker, no randomness, no
per-test uniqueness beyond what the tests ask for. When a test needs a
specific attribute, it passes it in; otherwise the defaults here are
the boring middle of the road.

Session 8: make_employee no longer creates a ShiftPattern
automatically (the app no longer does either). Tests opt in with
with_pattern=True or cycle_weeks=N.

Branch A: roles moved from Employee.role to EmployeeTeam.role (per-team
TeamRole). make_employee still accepts role=<TeamRole> as a convenience
and creates the EmployeeTeam link for you.
"""

import uuid
from datetime import date, timedelta

from django.contrib.auth.models import Group, Permission, User
from django.utils import timezone

from schedule.models import (
    Company,
    CompanyMembership,
    Employee,
    EmployeeTeam,
    ShiftPattern,
    Team,
    TeamRole,
    Title,
)


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


def make_team(company=None, name="Test Team"):
    company = company or Company.objects.first() or make_company()
    team, _ = Team.objects.get_or_create(company=company, name=name)
    return team


def make_team_role(name="Receptionist", order=0, team=None, company=None):
    team = team or make_team(company=company)
    role, _ = TeamRole.objects.get_or_create(
        team=team, name=name, defaults={"display_order": order}
    )
    return role


def make_title(name="Dr.", company=None, team=None):
    """Return a Title, creating it if needed."""
    company = company or Company.objects.first() or make_company()
    title, _ = Title.objects.get_or_create(name=name, company=company, team=team)
    return title


def make_employee(
    email="test@example.com",
    company=None,
    start_date=None,
    with_pattern=False,
    **kwargs,
):
    role = kwargs.pop("role", None)
    cycle_weeks = kwargs.pop("cycle_weeks", None)
    if cycle_weeks is not None:
        with_pattern = True
    if cycle_weeks is None:
        cycle_weeks = 1

    if start_date is None:
        start_date = timezone.localdate()
        # Clamp Sunday to Saturday. The schedule week is Mon-Sat
        # (DAYS = [0..5]); on Sunday, timezone.localdate() is AFTER the
        # current week's Saturday, so _employees_for_week excludes
        # the employee. Tests using the default start_date pass on
        # Mon-Sat and would fail on Sunday without this clamp.
        if start_date.weekday() == 6:
            start_date -= timedelta(days=1)

    company = company or Company.objects.first() or make_company()
    employee = Employee.objects.create(
        first_name=kwargs.pop("first_name", "Test"),
        last_name=kwargs.pop("last_name", "User"),
        email=email,
        company=company,
        start_date=start_date,
        **kwargs,
    )

    if role is not None:
        EmployeeTeam.objects.update_or_create(
            employee=employee,
            team=role.team,
            defaults={"role": role, "is_default": True, "valid_from": start_date},
        )

    if with_pattern:
        anchor = employee.start_date - timedelta(days=employee.start_date.weekday())
        ShiftPattern.objects.create(
            employee=employee,
            effective_from=anchor,
            cycle_weeks=cycle_weeks,
        )

    return employee


def make_superuser(username="admin", company=None):
    """Superuser. Auto-joins the test's company (creating one if none)."""
    user = User.objects.create_superuser(
        username=username, password="pass", email=f"{username}@example.com"
    )
    company = company or Company.objects.order_by("id").first() or make_company()
    CompanyMembership.objects.create(
        user=user, company=company, role="admin", status="active"
    )
    return user


def make_staff_user(username="staff", company=None):
    """view_shift only. Member role — NOT a company admin."""
    user = User.objects.create_user(
        username=username, password="pass", email=f"{username}@example.com"
    )
    user.user_permissions.add(Permission.objects.get(codename="view_shift"))
    company = company or Company.objects.order_by("id").first() or make_company()
    CompanyMembership.objects.create(
        user=user, company=company, role="member", status="active"
    )
    return user


def make_member_user(username="member", company=None):
    """A plain authed user with an active membership but NO schedule perms."""
    user = User.objects.create_user(
        username=username, password="pass", email=f"{username}@example.com"
    )
    company = company or Company.objects.order_by("id").first() or make_company()
    CompanyMembership.objects.create(
        user=user, company=company, role="member", status="active"
    )
    return user


def make_viewer_user(username="viewer", company=None):
    """Authenticated company member with view_shift but no write permissions."""
    user = User.objects.create_user(
        username=username,
        password="pass",
        email=f"{username}@example.com",
    )
    perm = Permission.objects.get(
        codename="view_shift",
        content_type__app_label="schedule",
    )
    user.user_permissions.add(perm)
    company = company or Company.objects.order_by("id").first() or make_company()
    CompanyMembership.objects.create(
        user=user,
        company=company,
        role="member",
        status="active",
    )
    return user


def make_manager_user(username="manager", company=None):
    """All schedule perms, member role. Perm-only user — fails
    company_admin_required. Use make_management_user for admin."""
    user = User.objects.create_user(
        username=username, password="pass", email=f"{username}@example.com"
    )
    user.user_permissions.set(
        Permission.objects.filter(content_type__app_label="schedule")
    )
    company = company or Company.objects.order_by("id").first() or make_company()
    CompanyMembership.objects.create(
        user=user, company=company, role="member", status="active"
    )
    return user


def make_management_user(username="management", company=None):
    """All schedule perms + admin membership + Platform Admin group."""
    user = User.objects.create_user(
        username=username, password="pass", email=f"{username}@example.com"
    )
    user.user_permissions.set(
        Permission.objects.filter(content_type__app_label="schedule")
    )
    company = company or Company.objects.order_by("id").first() or make_company()
    CompanyMembership.objects.create(
        user=user, company=company, role="admin", status="active"
    )
    mgmt, _ = Group.objects.get_or_create(name="Platform Admin")
    user.groups.add(mgmt)
    return user


def next_monday(today=None):
    """The Monday of next week, relative to `today` (defaults to today)."""
    today = today or timezone.localdate()
    return today + timedelta(days=7 - today.weekday())
