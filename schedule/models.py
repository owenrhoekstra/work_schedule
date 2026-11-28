"""Domain models for the schedule app.

Multi-tenancy (Branch 1): every scheduling root carries a `company`
FK. `EmploymentPeriod` and `ShiftPattern` also carry a redundant
`company_id` for direct querying — their `save()` override keeps it
synced to `employee.company_id` so the column can't drift.

`Employee` is scheduling-only. Access (authz) is via
`CompanyMembership` and `TeamMembership` — a global `User` can be an
Employee at Company A and Company B simultaneously (one Employee row
per company), or a company admin without being on any schedule at all.
"""

from datetime import date

from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import UUID7


class Company(models.Model):
    """One tenant. Everything scheduling-scoped hangs off this."""

    id = models.UUIDField(primary_key=True, db_default=UUID7(), editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100, unique=True)
    domain = models.CharField(
        max_length=255,
        blank=True,
        help_text="Reserved for future per-tenant domain routing. Unused today.",
    )
    site_url = models.CharField(
        max_length=255,
        blank=True,
        help_text="Absolute base URL for building links in emails and QR codes.",
    )
    app_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Branded app name shown in the UI and emails.",
    )
    cycle_epoch = models.DateField(
        help_text="Anchor Monday for computing which week of a multi-week cycle a date falls on.",
    )
    allow_member_view_all = models.BooleanField(
        default=False,
        help_text=(
            "When true, any employed member can view the full company "
            "schedule via /api/v1/schedule/week/?scope=company. When "
            "false, company-wide viewing is limited to company admins."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "companies"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Team(models.Model):
    """A scheduling sub-scope inside a company (Kitchen, Front House, etc.)."""

    id = models.UUIDField(primary_key=True, db_default=UUID7(), editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="teams")
    name = models.CharField(max_length=100)
    allow_member_view_all = models.BooleanField(
        default=False,
        help_text=(
            "When true, team members may toggle their home view to see "
            "the whole team's schedule. When false, they see only their own."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["company", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"], name="unique_team_per_company"
            )
        ]

    def __str__(self):
        return f"{self.company.name} / {self.name}"


class CompanyMembership(models.Model):
    """Access grant: user can reach this company. Separate from Employee."""

    ROLE_ADMIN = "admin"
    ROLE_MEMBER = "member"
    ROLE_CHOICES = [
        (ROLE_ADMIN, "Admin"),
        (ROLE_MEMBER, "Member"),
    ]

    STATUS_PENDING = "pending"
    STATUS_ACTIVE = "active"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_ACTIVE, "Active"),
    ]

    id = models.UUIDField(primary_key=True, db_default=UUID7(), editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="company_memberships"
    )
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "company"], name="unique_company_membership"
            )
        ]

    def __str__(self):
        return f"{self.user} @ {self.company} ({self.role}/{self.status})"


class TeamMembership(models.Model):
    """Authz-scoped user↔team link. Carries history."""

    ROLE_ADMIN = "admin"
    ROLE_MEMBER = "member"
    ROLE_CHOICES = [
        (ROLE_ADMIN, "Admin"),
        (ROLE_MEMBER, "Member"),
    ]

    id = models.UUIDField(primary_key=True, db_default=UUID7(), editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="team_memberships"
    )
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    valid_from = models.DateField()
    valid_to = models.DateField(
        null=True,
        blank=True,
        help_text="Exclusive: first day no longer on this team. Null while current.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["team", "valid_from"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "team"],
                condition=models.Q(valid_to__isnull=True),
                name="unique_active_team_membership",
            )
        ]

    def __str__(self):
        end = self.valid_to.isoformat() if self.valid_to else "present"
        return f"{self.user} on {self.team} ({self.valid_from} → {end})"


class TeamRole(models.Model):
    """A cosmetic job label, scoped to one team.

    Replaces the company-level `Role` model. A team admin defines their
    own team's roles; a company admin defines all of them. Purely
    cosmetic — no authz, no schedule logic. Multi-team employees have a
    separate role per team (via EmployeeTeam.role).
    """

    id = models.UUIDField(primary_key=True, db_default=UUID7(), editable=False)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="team_roles")
    name = models.CharField(max_length=100)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "name"],
                name="unique_team_role_per_team",
            )
        ]

    def __str__(self):
        return f"{self.team.name} / {self.name}"


class Title(models.Model):
    """A name prefix (Dr., Mr., Mrs.), scoped per company or per team."""

    id = models.UUIDField(primary_key=True, db_default=UUID7(), editable=False)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="titles"
    )
    team = models.ForeignKey(
        Team,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="titles",
        help_text="Null = company-wide default. Set = team-scoped fork.",
    )
    name = models.CharField(max_length=20)
    display_order = models.PositiveIntegerField(default=0)
    show_in_name = models.BooleanField(
        default=True,
        help_text="Include this title when displaying the employee's full name.",
    )

    class Meta:
        ordering = ["display_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "team", "name"],
                name="unique_title_per_company_or_team",
                nulls_distinct=False,
            )
        ]

    def __str__(self):
        return self.name


class Employee(models.Model):
    """A person on the schedule. Scheduling-only — no authz here.

    `user` is a plain FK (nullable): an employee can exist before the
    person has an account, and one user can be an Employee at multiple
    companies. Access control lives on CompanyMembership.
    """

    id = models.UUIDField(primary_key=True, db_default=UUID7(), editable=False)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="employees"
    )
    title = models.ForeignKey(
        Title,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="employees",
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="employees",
    )
    is_active = models.BooleanField(default=True)
    show_team_schedules = models.BooleanField(
        default=True,
        help_text=(
            "Only relevant when the team's allow_member_view_all is true. "
            "When false, this employee's home view stays on their own schedule."
        ),
    )
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
                fields=["company", "email"],
                condition=models.Q(is_active=True),
                name="unique_active_employee_email_per_company",
                nulls_distinct=False,
            ),
            models.UniqueConstraint(
                fields=["user", "company"],
                condition=models.Q(user__isnull=False),
                name="unique_employee_per_user_per_company",
                nulls_distinct=False,
            ),
        ]

    def __str__(self):
        if self.title and self.title.show_in_name:
            return f"{self.title.name} {self.first_name} {self.last_name}"
        return f"{self.first_name} {self.last_name}"


class EmployeeTeam(models.Model):
    """Scheduling-scoped employee↔team link. Carries history + default flag."""

    id = models.UUIDField(primary_key=True, db_default=UUID7(), editable=False)
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="team_links"
    )
    team = models.ForeignKey(
        Team, on_delete=models.CASCADE, related_name="employee_links"
    )
    is_default = models.BooleanField(default=False)
    role = models.ForeignKey(
        "TeamRole",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="employee_team_assignments",
        help_text=(
            "Cosmetic role for this employee on this team. "
            "Independent per team — Alice can be Head Chef on Kitchen "
            "and Server on Front."
        ),
    )
    valid_from = models.DateField()
    valid_to = models.DateField(
        null=True,
        blank=True,
        help_text="Exclusive: first day no longer on this team. Null while current.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["employee", "valid_from"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "team"],
                condition=models.Q(valid_to__isnull=True),
                name="unique_active_employee_team",
            ),
            models.UniqueConstraint(
                fields=["employee"],
                condition=models.Q(is_default=True, valid_to__isnull=True),
                name="unique_default_employee_team",
            ),
        ]

    def __str__(self):
        return f"{self.employee} on {self.team}"


class EmploymentPeriod(models.Model):
    """One continuous stretch of employment for an Employee.

    `end_date` is exclusive. `company_id` is kept in sync with
    `employee.company_id` by `save()` so it can be queried directly
    without a join.
    """

    id = models.UUIDField(primary_key=True, db_default=UUID7(), editable=False)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="employment_periods"
    )
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

    def save(self, *args, **kwargs):
        if self.employee_id:
            self.company_id = self.employee.company_id
        super().save(*args, **kwargs)

    def __str__(self):
        end = self.end_date.isoformat() if self.end_date else "present"
        return f"{self.employee} {self.start_date} → {end}"


class ShiftPattern(models.Model):
    """A snapshot of an employee's default weekly schedule.

    `effective_to` is exclusive; null = open-ended. `company_id` kept
    in sync with `employee.company_id` by `save()`.
    """

    id = models.UUIDField(primary_key=True, db_default=UUID7(), editable=False)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="shift_patterns"
    )
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="patterns"
    )
    effective_from = models.DateField()
    effective_to = models.DateField(
        null=True,
        blank=True,
        help_text=(
            "Exclusive: first day this pattern no longer applies. "
            "Null while it runs indefinitely."
        ),
    )
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

    def save(self, *args, **kwargs):
        if self.employee_id:
            self.company_id = self.employee.company_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee} from {self.effective_from}"


class Shift(models.Model):
    """One cell of an employee's default weekly pattern. No company FK
    (derived via pattern → employee → company)."""

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
    """A one-off change for a single employee on a single date. No company FK."""

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
    """Whole-date status (Closed / Holiday). Company-wide when `team` is
    null, team-scoped otherwise."""

    STATUS_CLOSED = "closed"
    STATUS_HOLIDAY = "holiday"
    STATUS_CHOICES = [
        (STATUS_CLOSED, "Closed"),
        (STATUS_HOLIDAY, "Holiday"),
    ]

    id = models.UUIDField(primary_key=True, db_default=UUID7(), editable=False)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="day_overrides"
    )
    team = models.ForeignKey(
        Team,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="day_overrides",
        help_text="Null = whole-company status. Set = team-scoped.",
    )
    date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)

    class Meta:
        ordering = ["date"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "team", "date"],
                name="unique_day_override_per_company_team_date",
                nulls_distinct=False,
            )
        ]

    def __str__(self):
        return f"{self.date} — {self.get_status_display()}"
