from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone


class EmployeeDeactivationMiddleware:
    """Enforce Employee.last_day at request time.

    An employee is current through the end of their last_day. The day
    after, they're off. If an authenticated user is past that point and
    their User is still active, flip it off, log them out, and redirect.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user

        if user.is_authenticated:
            employee = getattr(user, "employee", None)
            if (
                employee
                and employee.last_day
                and employee.last_day < timezone.localdate()
                and user.is_active
            ):
                user.is_active = False
                user.save(update_fields=["is_active"])
                logout(request)
                messages.info(
                    request,
                    "Your account has been deactivated. If you think this is "
                    "a mistake, contact a manager.",
                )
                return redirect(reverse("login"))

        return self.get_response(request)
