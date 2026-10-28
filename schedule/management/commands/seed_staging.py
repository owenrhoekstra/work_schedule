"""Seed the staging database with sample data.

Only runs when settings.STAGING is true. Idempotent — every creation
uses get_or_create, so re-running doesn't duplicate.

States covered:
- Manager with 1-week pattern
- Reception with 2-week rotation + a one-off shift override
- Technician with a standard pattern
- Vet scheduled for deactivation in 14 days
- Receptionist who left 4 weeks ago (former employee)
- New hire with no schedule (empty state)
- One day-override (holiday) for a week in the near future
"""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from schedule.models import (
    DayOverride,
    Employee,
    EmploymentPeriod,
    Role,
    Shift,
    ShiftOverride,
    ShiftPattern,
    Title,
)


class Command(BaseCommand):
    help = "Seed staging database with sample data."

    def handle(self, *args, **options):
        if not settings.STAGING:
            raise CommandError(
                "Refusing to run: DJANGO_STAGING is not true. This "
                "command is for the staging environment only."
            )

        self._seed_roles()
        self._seed_titles()
        self._seed_employees()
        self.stdout.write(self.style.SUCCESS("Staging data seeded."))

    def _seed_roles(self):
        for name, order in [
            ("Manager", 10),
            ("Veterinarian", 20),
            ("Reception", 30),
            ("Technician", 40),
            ("Veterinary Assistant", 50),
        ]:
            Role.objects.get_or_create(
                name=name, defaults={"display_order": order}
            )
        self.stdout.write("  roles ready")

    def _seed_titles(self):
        Title.objects.get_or_create(name="Dr.", defaults={"display_order": 10})
        self.stdout.write("  titles ready")

    def _seed_employees(self):
        today = timezone.localdate()
        this_monday = today - timedelta(days=today.weekday())

        manager_role = Role.objects.get(name="Manager")
        reception_role = Role.objects.get(name="Reception")
        tech_role = Role.objects.get(name="Technician")
        vet_role = Role.objects.get(name="Veterinarian")

        # 1. Manager with 1-week pattern
        mgr, created = Employee.objects.get_or_create(
            email="manager@staging.example.com",
            defaults={
                "first_name": "Morgan",
                "last_name": "Manager",
                "role": manager_role,
                "start_date": this_monday - timedelta(weeks=52),
            },
        )
        if created:
            EmploymentPeriod.objects.create(
                employee=mgr, start_date=mgr.start_date, end_date=None
            )
            self._seed_pattern(
                mgr,
                this_monday - timedelta(weeks=52),
                1,
                {d: ("09:00", "17:00") for d in range(5)},
            )

        # 2. Reception with 2-week rotation + override
        recep, created = Employee.objects.get_or_create(
            email="reception@staging.example.com",
            defaults={
                "first_name": "Riley",
                "last_name": "Reception",
                "role": reception_role,
                "start_date": this_monday - timedelta(weeks=26),
            },
        )
        if created:
            EmploymentPeriod.objects.create(
                employee=recep, start_date=recep.start_date, end_date=None
            )
            self._seed_pattern(
                recep,
                this_monday - timedelta(weeks=26),
                2,
                {
                    **{(0, d): ("08:00", "16:00") for d in range(5)},
                    **{(1, d): ("12:00", "20:00") for d in range(5)},
                },
            )
            ShiftOverride.objects.get_or_create(
                employee=recep,
                date=this_monday + timedelta(days=2),
                defaults={"start_time": "10:00", "end_time": "18:00"},
            )

        # 3. Technician
        tech, created = Employee.objects.get_or_create(
            email="tech@staging.example.com",
            defaults={
                "first_name": "Taylor",
                "last_name": "Tech",
                "role": tech_role,
                "start_date": this_monday - timedelta(weeks=8),
            },
        )
        if created:
            EmploymentPeriod.objects.create(
                employee=tech, start_date=tech.start_date, end_date=None
            )
            self._seed_pattern(
                tech,
                this_monday - timedelta(weeks=8),
                1,
                {d: ("10:00", "18:00") for d in range(4)},
            )

        # 4. Vet scheduled for deactivation in 14 days
        leaving, created = Employee.objects.get_or_create(
            email="leaving@staging.example.com",
            defaults={
                "first_name": "Sam",
                "last_name": "Leaving",
                "role": vet_role,
                "start_date": this_monday - timedelta(weeks=12),
                "last_day": today + timedelta(days=14),
            },
        )
        if created:
            EmploymentPeriod.objects.create(
                employee=leaving,
                start_date=leaving.start_date,
                end_date=leaving.last_day + timedelta(days=1),
            )
            self._seed_pattern(
                leaving,
                this_monday - timedelta(weeks=12),
                1,
                {0: ("08:00", "14:00"), 2: ("08:00", "14:00"), 4: ("08:00", "14:00")},
            )

        # 5. Former employee (departed 4 weeks ago)
        former, created = Employee.objects.get_or_create(
            email="former@staging.example.com",
            defaults={
                "first_name": "Frances",
                "last_name": "Former",
                "role": reception_role,
                "start_date": this_monday - timedelta(weeks=104),
                "last_day": this_monday - timedelta(weeks=4),
                "is_active": False,
            },
        )
        if created:
            EmploymentPeriod.objects.create(
                employee=former,
                start_date=former.start_date,
                end_date=former.last_day + timedelta(days=1),
            )

        # 6. New hire, no schedule (empty state)
        Employee.objects.get_or_create(
            email="newhire@staging.example.com",
            defaults={
                "first_name": "Nora",
                "last_name": "Newhire",
                "role": reception_role,
                "start_date": this_monday,
            },
        )

        # Day override for next week (holiday)
        DayOverride.objects.get_or_create(
            date=this_monday + timedelta(weeks=1, days=3),
            defaults={"status": "holiday"},
        )

        self.stdout.write("  employees ready")

    def _seed_pattern(self, employee, effective_from, cycle_weeks, shifts):
        pattern, created = ShiftPattern.objects.get_or_create(
            employee=employee,
            effective_from=effective_from,
            defaults={"cycle_weeks": cycle_weeks, "effective_to": None},
        )
        if not created:
            return
        for key, (start, end) in shifts.items():
            if isinstance(key, tuple):
                week_offset, day = key
            else:
                week_offset, day = 0, key
            Shift.objects.create(
                pattern=pattern,
                week_offset=week_offset,
                day=day,
                start_time=start,
                end_time=end,
            )