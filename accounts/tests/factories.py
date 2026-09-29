from datetime import date

from django.contrib.auth.models import User

from schedule.models import Employee, Role


def make_role(name="Staff", order=10):
    role, _ = Role.objects.get_or_create(name=name, defaults={"display_order": order})
    return role


def make_employee(email="emp@example.com", **kwargs):
    return Employee.objects.create(
        first_name=kwargs.pop("first_name", "Test"),
        last_name=kwargs.pop("last_name", "User"),
        email=email,
        role=make_role(),
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
