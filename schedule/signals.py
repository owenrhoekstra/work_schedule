from datetime import timedelta

from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Employee, EmploymentPeriod


@receiver(post_save, sender=Employee)
def sync_employee_to_user(sender, instance, **kwargs):
    """Mirror Employee's canonical fields to the linked User.

    Employee is the source of truth for first_name, last_name, and email.
    Uses queryset.update() so User.post_save doesn't fire — no loop risk.
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

    `end_date` is exclusive, so it's `last_day + 1` when a last day is
    already known. Normally `last_day` is None on creation and the
    period stays open until the employee is deactivated.
    """
    if not created:
        return
    end_date = instance.last_day + timedelta(days=1) if instance.last_day else None
    EmploymentPeriod.objects.get_or_create(
        employee=instance,
        defaults={
            "start_date": instance.start_date,
            "end_date": end_date,
        },
    )
