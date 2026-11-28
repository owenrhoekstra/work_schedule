"""Backfill EmployeeTeam.role from the old Employee.role.

For each existing EmployeeTeam row whose employee has a role, create a
matching TeamRole on that team (idempotent via get_or_create) and link
the EmployeeTeam to it. Employees with a role but no team assignment
keep no team role — they'll show "—" in the schedule until a team
assignment is added.

Reverse is intentionally a no-op: undoing means dropping the TeamRole
rows, which the next migration (drop Role / drop Employee.role) handles.
"""

from django.db import migrations


def backfill(apps, schema_editor):
    EmployeeTeam = apps.get_model("schedule", "EmployeeTeam")
    TeamRole = apps.get_model("schedule", "TeamRole")

    for et in EmployeeTeam.objects.select_related("employee__role", "team"):
        old_role = getattr(et.employee, "role", None)
        if old_role is None:
            continue
        team_role, _ = TeamRole.objects.get_or_create(
            team=et.team,
            name=old_role.name,
            defaults={"display_order": old_role.display_order},
        )
        et.role = team_role
        et.save(update_fields=["role"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("schedule", "0009_add_teamrole_and_employee_team_role"),
    ]
    operations = [
        migrations.RunPython(backfill, noop),
    ]
