"""Create the seed Company and backfill `company` FKs on existing rows.

Run once after `migrate` on a fresh DB. Idempotent — safe to re-run.

Backfills three things:
    1. `company` FK on every domain root that has NULL (Employee,
       EmploymentPeriod, ShiftPattern, DayOverride, Title)
  2. Active member CompanyMemberships for every active Employee with
     a linked User who doesn't already have a membership at this
     company (mirrors migration 0007)
  3. Optionally (via --migrate-management-admins), active admin
     CompanyMemberships for every Management / Platform Admin group
     member. Use for the seed company only — subsequent companies
     shouldn't auto-grant platform admins as their admins.
"""

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from schedule.models import (
    Company,
    CompanyMembership,
    DayOverride,
    Employee,
    EmploymentPeriod,
    ShiftPattern,
    Title,
)

_BACKFILL_MODELS = (
    Employee,
    EmploymentPeriod,
    ShiftPattern,
    DayOverride,
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
                "Convert every Management / Platform Admin group member "
                "to an active company admin for this company. Use once "
                "for the seed company; leave off for subsequent "
                "companies."
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

            # Active member memberships for every linked, active Employee.
            # Mirrors migration 0007's logic; safe to re-run because
            # get_or_create won't downgrade an existing admin membership.
            staff_created = 0
            for emp in Employee.objects.filter(
                company=company, is_active=True, user__isnull=False
            ).iterator():
                _, was_created = CompanyMembership.objects.get_or_create(
                    user_id=emp.user_id,
                    company_id=emp.company_id,
                    defaults={"role": "member", "status": "active"},
                )
                if was_created:
                    staff_created += 1
            if staff_created:
                self.stdout.write(f"  Backfilled {staff_created} Staff membership(s).")

            if options["migrate_management_admins"]:
                # Accept both group names. Migration 0006 renamed
                # Management → Platform Admin. A DB that has run 0006
                # only has Platform Admin; a DB that hasn't (unlikely
                # at this point) only has Management. Iterate both.
                admin_users = User.objects.filter(
                    groups__name__in=["Management", "Platform Admin"]
                ).distinct()
                if not admin_users.exists():
                    self.stdout.write(
                        "No Management or Platform Admin group members found; "
                        "skipping admin migration."
                    )
                else:
                    count = 0
                    for user in admin_users:
                        _, was_created = CompanyMembership.objects.get_or_create(
                            user=user,
                            company=company,
                            defaults={"role": "admin", "status": "active"},
                        )
                        if was_created:
                            count += 1
                    self.stdout.write(
                        f"  Converted {count} admin(s) to company admins."
                    )
