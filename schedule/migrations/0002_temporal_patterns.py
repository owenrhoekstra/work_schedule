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

This migration is irreversible. Rolling back would need to restore
Shift.employee from values that were dropped, and there's no way to
reconstruct that mapping. A database backup is the only safe path.
"""

from datetime import timedelta

import django.db.models.deletion
from django.db import migrations, models
from django.db.migrations.exceptions import IrreversibleError
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


def _irreversible(apps, schema_editor):
    """Refuse to reverse this migration.

    The forward path dropped Shift.employee, and its values are gone.
    Reversing would leave Shift rows orphaned and could only partially
    reconstruct Employee.cycle_weeks. Restore from a database backup
    instead.
    """
    raise IrreversibleError(
        "Cannot reverse schedule.0002_temporal_patterns — the previous "
        "Shift.employee column has been dropped and its values are gone. "
        "Restore from a database backup instead."
    )


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
                            "Length of the repeating schedule pattern, in weeks (1–4)."
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
        migrations.RunPython(backfill_patterns, migrations.RunPython.noop),
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
        # ----- Guard against rollback -------------------------------------
        # On forward: no-op. On reverse: runs first (reverse order) and
        # raises before any of the schema changes above get undone.
        migrations.RunPython(migrations.RunPython.noop, _irreversible),
    ]
