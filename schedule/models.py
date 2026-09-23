from django.contrib.auth.models import User
from django.db import models


class Title(models.Model):
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
    name = models.CharField(max_length=100, unique=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name


class Employee(models.Model):
    title = models.ForeignKey(
        Title,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="employees",
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    role = models.ForeignKey(
        Role,
        on_delete=models.PROTECT,
        related_name="employees",
    )
    email = models.EmailField()
    user = models.OneToOneField(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="employee",
    )
    is_active = models.BooleanField(default=True)
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


class Shift(models.Model):
    DAY_CHOICES = [
        (0, "Monday"),
        (1, "Tuesday"),
        (2, "Wednesday"),
        (3, "Thursday"),
        (4, "Friday"),
        (5, "Saturday"),
    ]

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="shifts"
    )
    day = models.IntegerField(choices=DAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        unique_together = ("employee", "day")


class ShiftOverride(models.Model):
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="overrides"
    )
    date = models.DateField()
    is_off = models.BooleanField(default=False)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)

    class Meta:
        unique_together = ("employee", "date")
