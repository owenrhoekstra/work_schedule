"""Rename the Management group to Platform Admin.

Branch 2 replaces the Management-group authz gate with
CompanyMembership-derived company/team admin checks. The group stays
as a data flag for `is_platform_admin`, but its name changes to
reflect its new scope: platform-level, not per-company.

Idempotent. No-op if Management doesn't exist. Leaves Platform Admin
alone if it already exists (a fresh DB that only ever used the new
name).
"""

from django.db import migrations


def rename_management_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    try:
        mgmt = Group.objects.get(name="Management")
    except Group.DoesNotExist:
        return
    if Group.objects.filter(name="Platform Admin").exists():
        return
    mgmt.name = "Platform Admin"
    mgmt.save(update_fields=["name"])


def unrename_management_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    try:
        pa = Group.objects.get(name="Platform Admin")
    except Group.DoesNotExist:
        return
    if Group.objects.filter(name="Management").exists():
        return
    pa.name = "Management"
    pa.save(update_fields=["name"])


class Migration(migrations.Migration):
    dependencies = [
        ("schedule", "0005_tighten_company_fks"),
    ]

    operations = [
        migrations.RunPython(rename_management_group, unrename_management_group),
    ]
