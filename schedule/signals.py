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
    if created:
        EmploymentPeriod.objects.create(
            employee=instance,
            start_date=instance.start_date,
            end_date=instance.inactivated_on,
        )
