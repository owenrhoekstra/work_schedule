from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone


class EmployeeDeactivationMiddleware:
    """Enforce Employee.last_day for the currently-selected company.

    Branch 2 rewrite. Previous version used `user.employees.first()`
    across all companies and flipped the shared `User.is_active` flag
    — which logged a user out of every company and disabled their
    account everywhere when they were deactivated at just one.

    New behavior:
      - Scoped to `request.company`, not `.first()` across all
        companies.
      - Does not touch `User.is_active`. Account status and employment
        status are separate concerns.
      - Acts as defense-in-depth. TenantMiddleware._resolve_company
        already filters deactivated companies out of its viable set,
        so in normal operation this middleware never fires. It
        remains to catch the (unlikely) case where a deactivation
        lands between middleware resolution and the view, and to
        provide a clean "employment ended" message instead of a
        silent redirect.

    On match: log out, redirect to login, surface a message.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if not user.is_authenticated:
            return self.get_response(request)

        company = getattr(request, "company", None)
        if company is None:
            return self.get_response(request)

        employee = user.employees.filter(company=company).first()
        if not (
            employee and employee.last_day and employee.last_day < timezone.localdate()
        ):
            return self.get_response(request)

        logout(request)
        messages.info(
            request,
            "Your employment at this company has ended. "
            "If you think this is a mistake, contact a manager.",
        )
        return redirect(reverse("login"))
