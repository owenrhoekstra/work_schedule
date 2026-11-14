"""Create the seed Company and backfill `company` FKs on existing rows.

Run once between migration 0001 and 0002 on an existing DB, or once
after `migrate` on a fresh DB. Idempotent — safe to re-run.
"""

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction

from schedule.models import (
    Company,
    CompanyMembership,
    DayOverride,
    Employee,
    EmploymentPeriod,
    Role,
    ShiftPattern,
    Title,
)


_BACKFILL_MODELS = (
    Employee,
    EmploymentPeriod,
    ShiftPattern,
    DayOverride,
    Role,
    Title,
)


class Command(BaseCommand):
    help = "Create the seed company and backfill company FKs."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True)
        parser.add_argument("--slug", required=True)
        parser.add_argument(
            "--site-url",
            default=None,
            help="Defaults to settings.SITE_URL.",
        )
        parser.add_argument(
            "--app-name",
            default=None,
            help="Defaults to settings.APP_NAME.",
        )
        parser.add_argument(
            "--migrate-management-admins",
            action="store_true",
            help=(
                "Convert every Management-group member to an active "
                "company admin for this company. Use once for the seed "
                "company; leave off for subsequent companies."
            ),
        )

    def handle(self, **options):
        site_url = options["site_url"] or settings.SITE_URL
        app_name = options["app_name"] or settings.APP_NAME

        with transaction.atomic():
            company, created = Company.objects.get_or_create(
                slug=options["slug"],
                defaults={
                    "name": options["name"],
                    "site_url": site_url,
                    "app_name": app_name,
                    "cycle_epoch": settings.CYCLE_EPOCH,
                },
            )
            state = "Created" if created else "Already exists:"
            self.stdout.write(f"{state} company {company.name!r} ({company.slug}).")

            for model in _BACKFILL_MODELS:
                updated = model.objects.filter(company__isnull=True).update(
                    company=company
                )
                if updated:
                    self.stdout.write(
                        f"  Backfilled {updated} {model.__name__} row(s)."
                    )

            if options["migrate_management_admins"]:
                try:
                    mgmt = Group.objects.get(name="Management")
                except Group.DoesNotExist:
                    self.stdout.write(
                        "No 'Management' group found; skipping admin migration."
                    )
                else:
                    count = 0
                    for user in mgmt.user_set.all():
                        _, was_created = CompanyMembership.objects.get_or_create(
                            user=user,
                            company=company,
                            defaults={"role": "admin", "status": "active"},
                        )
                        if was_created:
                            count += 1
                    self.stdout.write(
                        f"  Converted {count} Management-group member(s) "
                        f"to company admins."
                    )