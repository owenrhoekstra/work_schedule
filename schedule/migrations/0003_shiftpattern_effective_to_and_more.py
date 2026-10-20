"""Add explicit end date to ShiftPattern, sync cycle_weeks validators.

Each pattern now has an exclusive effective_to. Existing patterns are
backfilled so each one ends at the next pattern's start, and the last
pattern for each employee stays open-ended (effective_to = None).

Also syncs the shiftpattern.cycle_weeks field state to include the
MinValueValidator(1) and MaxValueValidator(4) that the model declares.
Those validators have existed on the model since 0002 but were never
captured in migration state, which was producing a perpetual
"makemigrations wants to alter cycle_weeks" warning. Folding that
AlterField in here clears the drift without a separate empty migration.

No behavior change in this migration. The resolution logic and form
still use pre-redesign semantics; the new field is populated but not
yet read.
"""

import django.core.validators
from django.db import migrations, models


def backfill_effective_to(apps, schema_editor):
    ShiftPattern = apps.get_model("schedule", "ShiftPattern")

    employee_ids = (
        ShiftPattern.objects.values_list("employee_id", flat=True).distinct()
    )

    for emp_id in employee_ids:
        patterns = list(
            ShiftPattern.objects.filter(employee_id=emp_id).order_by(
                "effective_from"
            )
        )
        for i, pattern in enumerate(patterns):
            if i + 1 < len(patterns):
                pattern.effective_to = patterns[i + 1].effective_from
            else:
                pattern.effective_to = None
            pattern.save(update_fields=["effective_to"])


class Migration(migrations.Migration):
    dependencies = [
        ("schedule", "0002_temporal_patterns"),
    ]

    operations = [
        # Sync cycle_weeks field state. Validators were declared on the
        # model in 0002 but never captured in migration state, causing
        # makemigrations to want to add this AlterField on every run.
        migrations.AlterField(
            model_name="shiftpattern",
            name="cycle_weeks",
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text=(
                    "Length of the repeating schedule pattern, in weeks (1–4)."
                ),
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(4),
                ],
            ),
        ),
        migrations.AddField(
            model_name="shiftpattern",
            name="effective_to",
            field=models.DateField(
                null=True,
                blank=True,
                help_text=(
                    "Exclusive: first day this pattern no longer applies. "
                    "Null while it runs indefinitely."
                ),
            ),
        ),
        migrations.RunPython(backfill_effective_to, migrations.RunPython.noop),
    ]