"""Backfill active CompanyMemberships for existing Staff employees.

Migration 0005 only backfilled CompanyMembership for old Management-
group members. Existing Staff employees with a linked User got their
Employee row's company_id backfilled but no membership. With
TENANT_ENFORCEMENT enabled by default, they'd log in and hit
/accounts/waiting/ despite being employed and approved.

Backfill: for every active Employee with a linked User, ensure the
User has an active CompanyMembership at the Employee's company. Uses
get_or_create with role="member" in defaults — if an active
admin membership already exists for that (user, company), no change
is made (no downgrade).
"""

from django.db import migrations


def backfill_staff_memberships(apps, schema_editor):
    Employee = apps.get_model("schedule", "Employee")
    CompanyMembership = apps.get_model("schedule", "CompanyMembership")

    created = 0
    for emp in (
        Employee.objects.filter(is_active=True, user__isnull=False)
        .select_related("company")
        .iterator()
    ):
        _, was_created = CompanyMembership.objects.get_or_create(
            user_id=emp.user_id,
            company_id=emp.company_id,
            defaults={"role": "member", "status": "active"},
        )
        if was_created:
            created += 1

    if created:
        print(f"  Backfilled {created} Staff company membership(s).")


def noop_reverse(apps, schema_editor):
    """No reverse — if a deploy is rolled back to 0006, the Staff
    memberships stay. They're harmless and would be re-created by
    re-running 0007."""


class Migration(migrations.Migration):
    dependencies = [
        ("schedule", "0006_rename_management_group"),
    ]

    operations = [
        migrations.RunPython(backfill_staff_memberships, noop_reverse),
    ]