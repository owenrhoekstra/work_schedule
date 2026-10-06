"""Introduce ShiftPattern and move Shift's ownership from Employee to it.

Hand-written because the shift requires re-pointing every existing Shift
row from an employee FK to a pattern FK, and Django can't generate that
automatically.

Two subtleties that the auto-generated migration can't handle:

1. The old (employee, week_offset, day) unique constraint on Shift must
   be dropped BEFORE the employee field is removed. If it isn't, Django's
   migration state keeps a reference to a field that no longer exists,
   and any future AlterUniqueTogether operation on Shift fails.
2. The new (pattern, week_offset, day) constraint is added at the end,
   once the pattern column is fully populated.

The backfill normalizes each pattern's effective_from to the Monday of
its anchor week so all patterns align with the week-based schedule view.
"""

import django.db.models.deletion
from datetime import timedelta

from django.db import migrations, models
from django.db.models.functions import UUID7


def backfill_patterns(apps, schema_editor):
    """Give every employee a ShiftPattern and re-point their shifts."""
    Employee = apps.get_model("schedule", "Employee")
    ShiftPattern = apps.get_model("schedule", "ShiftPattern")
    Shift = apps.get_model("schedule", "Shift")
    EmploymentPeriod = apps.get_model("schedule", "EmploymentPeriod")

    for emp in Employee.objects.all():
        earliest = (
            EmploymentPeriod.objects.filter(employee=emp)
            .order_by("start_date")
            .values_list("start_date", flat=True)
            .first()
        )
        anchor = earliest or emp.start_date
        # Normalize to Monday so patterns align with the week view
        anchor = anchor - timedelta(days=anchor.weekday())

        pattern = ShiftPattern.objects.create(
            employee=emp,
            effective_from=anchor,
            cycle_weeks=emp.cycle_weeks,
        )
        Shift.objects.filter(employee=emp).update(pattern=pattern)


def reverse_patterns(apps, schema_editor):
    """Best-effort reverse: collapse each employee's earliest pattern back
    into employee.cycle_weeks. Shifts are removed by FK cascade when the
    pattern column is dropped."""
    Employee = apps.get_model("schedule", "Employee")
    ShiftPattern = apps.get_model("schedule", "ShiftPattern")

    for emp in Employee.objects.all():
        first = (
            ShiftPattern.objects.filter(employee=emp)
            .order_by("effective_from")
            .first()
        )
        if first:
            emp.cycle_weeks = first.cycle_weeks
            emp.save(update_fields=["cycle_weeks"])


class Migration(migrations.Migration):

    dependencies = [
        ("schedule", "0001_initial"),
    ]

    operations = [
        # ----- Create ShiftPattern ----------------------------------------
        migrations.CreateModel(
            name="ShiftPattern",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        db_default=UUID7(),
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("effective_from", models.DateField()),
                (
                    "cycle_weeks",
                    models.PositiveSmallIntegerField(
                        default=1,
                        help_text=(
                            "Length of the repeating schedule pattern, "
                            "in weeks (1–4)."
                        ),
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="patterns",
                        to="schedule.employee",
                    ),
                ),
            ],
            options={"ordering": ["effective_from"]},
        ),
        migrations.AddConstraint(
            model_name="shiftpattern",
            constraint=models.UniqueConstraint(
                fields=("employee", "effective_from"),
                name="unique_pattern_per_employee_per_date",
            ),
        ),

        # ----- Add Shift.pattern, populate, make required -----------------
        migrations.AddField(
            model_name="shift",
            name="pattern",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="shifts",
                to="schedule.shiftpattern",
            ),
        ),
        migrations.RunPython(backfill_patterns, reverse_patterns),
        migrations.AlterField(
            model_name="shift",
            name="pattern",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="shifts",
                to="schedule.shiftpattern",
            ),
        ),

        # ----- Drop old constraint, remove employee field -----------------
        # Order matters: AlterUniqueTogether must run while employee still
        # exists in state, so Django can find the old constraint's columns.
        migrations.AlterUniqueTogether(
            name="shift",
            unique_together=set(),
        ),
        migrations.RemoveField(model_name="shift", name="employee"),

        # ----- Add new constraint -----------------------------------------
        migrations.AlterUniqueTogether(
            name="shift",
            unique_together={("pattern", "week_offset", "day")},
        ),

        # ----- Drop cycle_weeks from Employee -----------------------------
        migrations.RemoveField(model_name="employee", name="cycle_weeks"),
    ]