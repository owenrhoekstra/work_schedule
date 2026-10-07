"""Domain models for the schedule app.

Ordering matters — Django resolves foreign keys at class definition
time, so a model must appear before any model that references it.
Title and Role come first; Employee depends on both; ShiftPattern and
Shift depend on Employee.
"""

from datetime import date

from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import UUID7


class Title(models.Model):
    """A name prefix (Dr., Mr., Mrs.) that employees may carry.

    `show_in_name` controls whether the title appears in the employee's
    display string. A title like "N/A" would set it to False so it's
    stored for records but doesn't clutter the schedule.
    """

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
    """A job function (Manager, Receptionist, etc.).

    Roles sort by display_order then name. Reordering from the Settings
    page renumbers every role in steps of 10 so new roles can be slotted
    in later without touching everything.
    """

    id = models.UUIDField(primary_key=True, db_default=UUID7(), editable=False)
    name = models.CharField(max_length=100, unique=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name


class Employee(models.Model):
    """A person on the schedule.

    An Employee can be deactivated (has a `last_day`) and later
    reactivated without losing history — see EmploymentPeriod for the
    employment windows and ShiftPattern for the schedule snapshots.

    The unique constraint on email applies only among active employees,
    so a departed employee's email can be reused by a new hire once
    they've fully left. `is_active` is toggled off the moment a
    deactivation is scheduled, which frees the email for reuse.
    """

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
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="employee",
    )
    is_active = models.BooleanField(default=True)
    start_date = models.DateField(
        default=date.today,
        help_text="First day on the schedule. Can be in the past.",
    )
    last_day = models.DateField(
        null=True,
        blank=True,
        help_text="Final day on the schedule. The employee is off from the day after.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

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
    """One continuous stretch of employment for an Employee.

    A new hire gets one period. Deactivating closes it (`end_date` set).
    Reactivating opens a new one. The schedule reads these to decide
    whether someone was employed on a given date.

    `end_date` is exclusive — it's the first day NOT employed. An open
    period (`end_date=None`) means the employee is currently employed.
    """

    id = models.UUIDField(primary_key=True, db_default=UUID7(), editable=False)
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="periods"
    )
    start_date = models.DateField()
    end_date = models.DateField(
        null=True,
        blank=True,
        help_text="Exclusive: first day NOT employed. Null while currently employed.",
    )

    class Meta:
        ordering = ["start_date"]

    def __str__(self):
        end = self.end_date.isoformat() if self.end_date else "present"
        return f"{self.employee} {self.start_date} → {end}"


class ShiftPattern(models.Model):
    """A snapshot of an employee's default weekly schedule.

    Each pattern is effective from a specific Monday through to the day
    before the next pattern starts. The employee's earliest pattern
    covers everything from their first employment period up to the
    effective_from of their second pattern, and so on.

    Cycle length lives here rather than on Employee so past weeks keep
    the cycle they were generated under — changing a 2-week rotation to
    3 weeks creates a new pattern and leaves the history intact.
    """

    id = models.UUIDField(primary_key=True, db_default=UUID7(), editable=False)
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="patterns"
    )
    effective_from = models.DateField()
    cycle_weeks = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(4)],
        help_text="Length of the repeating schedule pattern, in weeks (1–4).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["effective_from"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "effective_from"],
                name="unique_pattern_per_employee_per_date",
            )
        ]

    def __str__(self):
        return f"{self.employee} from {self.effective_from}"


class Shift(models.Model):
    """One cell of an employee's default weekly pattern.

    A shift lives inside a ShiftPattern, keyed by (week_offset, day).
    Missing combinations mean the employee is off that day — we don't
    store explicit OFF rows.
    """

    DAY_CHOICES = [
        (0, "Monday"),
        (1, "Tuesday"),
        (2, "Wednesday"),
        (3, "Thursday"),
        (4, "Friday"),
        (5, "Saturday"),
    ]

    id = models.UUIDField(primary_key=True, db_default=UUID7(), editable=False)
    pattern = models.ForeignKey(
        ShiftPattern, on_delete=models.CASCADE, related_name="shifts"
    )
    week_offset = models.PositiveSmallIntegerField(
        default=0,
        help_text="Which week of the employee's cycle this shift belongs to (0-indexed).",
    )
    day = models.IntegerField(choices=DAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        unique_together = ("pattern", "week_offset", "day")


class ShiftOverride(models.Model):
    """A one-off change for a single employee on a single date.

    Always takes precedence over the employee's default pattern for
    that date. `is_off=True` means the employee is off that day (an
    explicit override of a default shift). Otherwise start_time and
    end_time give the substitute hours.
    """

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
    """A whole-date override that affects every employee.

    Used for closures and holidays. When a date has a DayOverride, all
    employees' cells for that date show the status instead of their
    shift, and any per-employee overrides are ignored.
    """

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
