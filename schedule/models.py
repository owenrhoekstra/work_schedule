from datetime import date

from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import UUID7


class Title(models.Model):
    id = models.UUIDField(primary_key=True, db_default=UUID7(), editable=False)
    name = models.CharField(max_length=20, unique=True)
    display_order = models.PositiveIntegerField(default=0)
    show_in_name = models.BooleanField(
        default=True,
        help_text="Include this title when displaying the employee's full name.",
    )

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name


class Role(models.Model):
    id = models.UUIDField(primary_key=True, db_default=UUID7(), editable=False)
    name = models.CharField(max_length=100, unique=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name


class Employee(models.Model):
    id = models.UUIDField(primary_key=True, db_default=UUID7(), editable=False)
    title = models.ForeignKey(
        Title,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="employees",
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="employees")
    email = models.EmailField()
    user = models.OneToOneField(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="employee"
    )
    is_active = models.BooleanField(default=True)
    start_date = models.DateField(
        default=date.today,
        help_text="First day on the schedule. Can be in the past.",
    )
    cycle_weeks = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(4)],
        help_text="Length of the repeating schedule pattern, in weeks (1–4).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    inactivated_on = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["email"],
                condition=models.Q(is_active=True),
                name="unique_active_employee_email",
            )
        ]

    def __str__(self):
        if self.title and self.title.show_in_name:
            return f"{self.title.name} {self.first_name} {self.last_name}"
        return f"{self.first_name} {self.last_name}"


class EmploymentPeriod(models.Model):
    id = models.UUIDField(primary_key=True, db_default=UUID7(), editable=False)
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="periods"
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)  # null = currently employed

    class Meta:
        ordering = ["start_date"]

    def __str__(self):
        end = self.end_date.isoformat() if self.end_date else "present"
        return f"{self.employee} {self.start_date} → {end}"


class Shift(models.Model):
    """Default shift for one day of one cycle week."""

    DAY_CHOICES = [
        (0, "Monday"),
        (1, "Tuesday"),
        (2, "Wednesday"),
        (3, "Thursday"),
        (4, "Friday"),
        (5, "Saturday"),
    ]

    id = models.UUIDField(primary_key=True, db_default=UUID7(), editable=False)
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="shifts"
    )
    week_offset = models.PositiveSmallIntegerField(
        default=0,
        help_text="Which week of the employee's cycle this shift belongs to (0-indexed).",
    )
    day = models.IntegerField(choices=DAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        unique_together = ("employee", "week_offset", "day")


class ShiftOverride(models.Model):
    id = models.UUIDField(primary_key=True, db_default=UUID7(), editable=False)
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="overrides"
    )
    date = models.DateField()
    is_off = models.BooleanField(default=False)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)

    class Meta:
        unique_together = ("employee", "date")


class DayOverride(models.Model):
    STATUS_CLOSED = "closed"
    STATUS_HOLIDAY = "holiday"
    STATUS_CHOICES = [
        (STATUS_CLOSED, "Closed"),
        (STATUS_HOLIDAY, "Holiday"),
    ]

    id = models.UUIDField(primary_key=True, db_default=UUID7(), editable=False)
    date = models.DateField(unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.date} — {self.get_status_display()}"
