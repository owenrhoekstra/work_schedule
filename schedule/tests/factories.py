"""Test factories for the schedule app.

Each helper is deliberately simple — no faker, no randomness, no
per-test uniqueness beyond what the tests ask for. When a test needs a
specific attribute, it passes it in; otherwise the defaults here are
the boring middle of the road.

Session 8: make_employee no longer creates a ShiftPattern
automatically (the app no longer does either). Tests opt in with
with_pattern=True or cycle_weeks=N.
"""

from datetime import date, timedelta

from django.contrib.auth.models import Permission, User

from schedule.models import Employee, Role, ShiftPattern, Title


def make_role(name="Staff", order=10):
    """Return a Role, creating it if needed.

    Idempotent — repeated calls with the same name return the same row.
    """
    role, _ = Role.objects.get_or_create(name=name, defaults={"display_order": order})
    return role


def make_title(name="Dr."):
    """Return a Title, creating it if needed."""
    title, _ = Title.objects.get_or_create(name=name)
    return title


def make_employee(
    email="test@example.com",
    role=None,
    start_date=None,
    with_pattern=False,
    **kwargs,
):
    """Create an Employee, optionally with an empty starting ShiftPattern.

    Post-Session 8, Employee creation no longer auto-creates a pattern
    — matching the app, where new hires have no schedule until a
    manager sets one up. Tests that need a pattern opt in.

    Args:
        with_pattern: create an empty open-ended ShiftPattern anchored
            to the Monday of start_date. Defaults to False.
        cycle_weeks: shorthand for with_pattern=True with the given
            cycle length (1–4). Passing this kwarg at all implies
            with_pattern=True, including cycle_weeks=1.

    Any remaining kwargs are passed through to Employee.objects.create.
    """
    cycle_weeks = kwargs.pop("cycle_weeks", None)
    if cycle_weeks is not None:
        with_pattern = True
    if cycle_weeks is None:
        cycle_weeks = 1

    role = role or make_role()
    employee = Employee.objects.create(
        first_name=kwargs.pop("first_name", "Test"),
        last_name=kwargs.pop("last_name", "User"),
        email=email,
        role=role,
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

    Note: `management_required` checks group membership by name
    ("Management"), not permissions. Tests that need to hit management
    views must additionally add this user to a Management group. See
    `ManagementRequiredTests` for the pattern.
    """
    user = User.objects.create_user(
        username=username, password="pass", email=f"{username}@example.com"
    )
    for codename in (
        "view_shift",
        "view_employee",
        "change_shift",
        "add_shift",
        "delete_shift",
        "add_employee",
        "change_employee",
        "delete_employee",
    ):
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return user


def next_monday(today=None):
    """The Monday of next week, relative to `today` (defaults to today)."""
    today = today or date.today()
    return today + timedelta(days=7 - today.weekday())