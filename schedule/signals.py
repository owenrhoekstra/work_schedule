"""Model signals for the schedule app.

Auto-creating an EmploymentPeriod when an Employee is first created.

ShiftPattern creation is NOT automatic. A newly created employee has
no schedule until a manager sets one up via /schedule/add/. This
matches the redesign's intent: reading is a summary, writing is a
deliberate action.

The former Employee → User sync signal was removed in Branch 1. Under
the split-membership model, `User` is the source of truth for identity
and email; `Employee` holds scheduling data. Mirroring Employee → User
meant a user employed at two companies had their name clobbered by
whichever Employee saved last. Profile edits flow through
`accounts.forms.ProfileForm`, which writes both rows together.
"""

from datetime import timedelta

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Employee, EmploymentPeriod


@receiver(post_save, sender=Employee)
def ensure_employee_has_period(sender, instance, created, **kwargs):
    """Create an EmploymentPeriod for a newly created Employee.

    `end_date` is exclusive, so when a last_day is already known it's
    `last_day + 1`. Normally `last_day` is None on creation and the
    period stays open.
    """
    if not created:
        return
    end_date = instance.last_day + timedelta(days=1) if instance.last_day else None
    EmploymentPeriod.objects.get_or_create(
        employee=instance,
        defaults={"start_date": instance.start_date, "end_date": end_date},
    )
