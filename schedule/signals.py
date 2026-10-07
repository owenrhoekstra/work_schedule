"""Model signals for the schedule app.

Two concerns:

- Keeping User and Employee in sync (name, email) so downstream code
  that reads either one sees consistent data.
- Auto-creating EmploymentPeriod and ShiftPattern rows when an
  Employee is first created, so new employees are immediately
  schedulable without a separate setup step.
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Employee, EmploymentPeriod, ShiftPattern


@receiver(post_save, sender=Employee)
def sync_employee_to_user(sender, instance, **kwargs):
    """Mirror Employee's canonical fields to the linked User.

    Employee is the source of truth for first_name, last_name, and
    email. Uses queryset.update() so User.post_save doesn't fire —
    no loop risk.
    """
    if not instance.user_id:
        return
    User.objects.filter(pk=instance.user_id).update(
        first_name=instance.first_name,
        last_name=instance.last_name,
        email=instance.email,
    )


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


@receiver(post_save, sender=Employee)
def ensure_employee_has_pattern(sender, instance, created, **kwargs):
    """Create an initial ShiftPattern for a newly created Employee.

    Anchored at the earliest employment period start, or the employee's
    start_date if no periods exist yet. The pattern starts empty — the
    manager fills in hours on the defaults page.

    If a pattern was somehow created manually before the signal ran,
    this is a no-op thanks to the exists() check.
    """
    if not created:
        return
    if instance.patterns.exists():
        return
    earliest = (
        instance.periods.order_by("start_date")
        .values_list("start_date", flat=True)
        .first()
    )
    anchor = earliest or instance.start_date
    # Normalize to Monday so pattern dates align with week-based lookups
    anchor = anchor - timedelta(days=anchor.weekday())
    ShiftPattern.objects.create(
        employee=instance,
        effective_from=anchor,
        cycle_weeks=1,
    )
