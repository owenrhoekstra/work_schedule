"""Backfill CompanyMemberships for existing Staff employees.

Migration 0005 only backfilled CompanyMembership for old Management-
group members. Existing Staff employees with a linked User got their
Employee row's company_id backfilled but no membership. With
TENANT_ENFORCEMENT enabled by default, they'd log in and hit
/accounts/waiting/ despite being employed and approved.

Status mirrors the User account state:
  - Active User + linked Employee → active membership (approved,
    ready to use)
  - Inactive User + linked Employee → pending membership (awaiting
    manager approval, appears in the pending queue)

The distinction matters for pre-Batch-2b password signups: they have
is_active=False and no membership yet. If we backfilled them straight
to active, they'd disappear from the approval queue (pending
memberships only) and never complete signup. Pending preserves their
state; approve_account then activates both the membership and the
User in one step.

New signups go through verify_signup_otp, which creates the
membership directly — this migration only touches pre-existing rows.

Local dev DBs that already ran the old (buggy) version of this
migration must be rebuilt (flush + restore, or full re-migrate on
empty DB). No follow-up migration: 0007 hasn't touched staging or
prod yet, so editing in place is safe.
"""

from django.db import migrations


def backfill_staff_memberships(apps, schema_editor):
    Employee = apps.get_model("schedule", "Employee")
    CompanyMembership = apps.get_model("schedule", "CompanyMembership")

    created_active = 0
    created_pending = 0

    for emp in (
        Employee.objects.filter(is_active=True, user__isnull=False)
        .select_related("user", "company")
        .iterator()
    ):
        status = "active" if emp.user.is_active else "pending"
        _, was_created = CompanyMembership.objects.get_or_create(
            user_id=emp.user_id,
            company_id=emp.company_id,
            defaults={"role": "member", "status": status},
        )
        if was_created:
            if status == "active":
                created_active += 1
            else:
                created_pending += 1

    if created_active or created_pending:
        print(
            f"  Backfilled {created_active} active and "
            f"{created_pending} pending Staff membership(s)."
        )


def noop_reverse(apps, schema_editor):
    """No reverse — if rolled back to 0006, the backfilled memberships
    stay. They're harmless and re-created by re-running 0007."""


class Migration(migrations.Migration):
    dependencies = [
        ("schedule", "0006_rename_management_group"),
    ]

    operations = [
        migrations.RunPython(backfill_staff_memberships, noop_reverse),
    ]
