"""Test factories for the schedule app.

Each helper is deliberately simple — no faker, no randomness, no
per-test uniqueness beyond what the tests ask for. When a test needs a
specific attribute, it passes it in; otherwise the defaults here are
the boring middle of the road.
"""

from datetime import date, timedelta

from django.contrib.auth.models import Permission, User

from schedule.models import Employee, Role, Title


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


def make_employee(email="test@example.com", role=None, start_date=None, **kwargs):
    """Create an Employee and ensure they have a starting ShiftPattern.

    The post_save signal on Employee creates the initial pattern, so by
    the time this returns `employee.patterns.first()` is guaranteed to
    exist. If `cycle_weeks` is passed, it's applied to that initial
    pattern rather than to the Employee (which no longer has the field).
    """
    cycle_weeks = kwargs.pop("cycle_weeks", 1)
    role = role or make_role()
    employee = Employee.objects.create(
        first_name=kwargs.pop("first_name", "Test"),
        last_name=kwargs.pop("last_name", "User"),
        email=email,
        role=role,
        start_date=start_date or date.today(),
        **kwargs,
    )
    if cycle_weeks != 1:
        pattern = employee.patterns.first()
        pattern.cycle_weeks = cycle_weeks
        pattern.save(update_fields=["cycle_weeks"])
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
    ):
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return user


def next_monday(today=None):
    """The Monday of next week, relative to `today` (defaults to today)."""
    today = today or date.today()
    return today + timedelta(days=7 - today.weekday())