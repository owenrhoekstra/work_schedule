from datetime import date, timedelta

from django.contrib.auth.models import Permission, User

from schedule.models import Employee, Role, Title


def make_role(name="Staff", order=10):
    role, _ = Role.objects.get_or_create(name=name, defaults={"display_order": order})
    return role


def make_title(name="Dr."):
    title, _ = Title.objects.get_or_create(name=name)
    return title


def make_employee(email="test@example.com", role=None, start_date=None, **kwargs):
    role = role or make_role()
    return Employee.objects.create(
        first_name=kwargs.pop("first_name", "Test"),
        last_name=kwargs.pop("last_name", "User"),
        email=email,
        role=role,
        start_date=start_date or date.today(),
        **kwargs,
    )


def make_superuser(username="admin"):
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
    """A user with all schedule permissions but no superuser flag."""
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
    """The Monday of next week."""
    today = today or date.today()
    return today + timedelta(days=7 - today.weekday())
