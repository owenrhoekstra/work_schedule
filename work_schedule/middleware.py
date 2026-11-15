from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone


class TenantMiddleware:
    """Resolve request.company and populate the admin-ladder flags.

    Commit 2 of Branch 2: adds is_platform_admin / is_company_admin /
    is_team_admin to the request. Decorators and the accounts context
    processor read these instead of re-querying per call.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.company = None
        request.team = None
        request.is_platform_admin = False
        request.is_company_admin = False
        request.is_team_admin = False

        if request.user.is_authenticated:
            request.company = self._resolve_company(request)
            from work_schedule.auth import (
                is_company_admin,
                is_platform_admin,
                is_team_admin,
            )

            request.is_platform_admin = is_platform_admin(request.user)
            request.is_company_admin = is_company_admin(request.user, request.company)
            request.is_team_admin = is_team_admin(
                request.user, request.team, request.company
            )

        return self.get_response(request)

    def _resolve_company(self, request):
        from schedule.models import Company, CompanyMembership

        session_id = request.session.get("company_id")
        if session_id:
            try:
                return Company.objects.get(pk=session_id)
            except Company.DoesNotExist, ValueError:
                request.session.pop("company_id", None)

        if request.user.is_superuser:
            return Company.objects.order_by("id").first()

        memberships = CompanyMembership.objects.filter(
            user=request.user, status="active"
        ).select_related("company")

        if memberships.count() == 1:
            company = memberships.first().company
            request.session["company_id"] = str(company.id)
            return company

        return None


class HTMXLoginRedirectMiddleware:
    """Convert login-redirects for HTMX requests into HX-Redirect.

    HTMX follows 3xx via browser fetch automatically. When a session
    expires and an HTMX form POST hits an `@login_required` view,
    Django returns 302 → /accounts/login/. HTMX follows it, gets the
    login page HTML (200), and swaps it into the fragment's hx-target
    — usually #schedule-table or a modal body. The user sees the login
    form embedded in a broken page, and loses their typed input.

    Detect that case (HX-Request header set + 3xx to LOGIN_URL) and
    rewrite: 204 with `HX-Redirect` header set to the login URL. HTMX
    performs a full-page navigation on HX-Redirect regardless of the
    target. The `?next=` query string is preserved, so the login view
    bounces the user back to the form after re-auth.

    Also catches the deactivation middleware's 302-to-login — same
    failure mode, same fix.

    Scoped to LOGIN_URL on purpose: an HTMX-facing view that returns a
    non-login 3xx (e.g. a future POST-redirect-GET) would be left
    alone. Extend the check if that assumption ever changes.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.login_prefix = settings.LOGIN_URL

    def __call__(self, request):
        response = self.get_response(request)

        if request.headers.get("HX-Request") != "true":
            return response

        if response.status_code not in (301, 302, 303, 307, 308):
            return response

        location = response.get("Location", "")
        if not location.startswith(self.login_prefix):
            return response

        # 204 = no swap, no error. HX-Redirect triggers a full-page
        # navigation to the location, including any ?next= param.
        redirect_response = HttpResponse(status=204)
        redirect_response["HX-Redirect"] = location
        return redirect_response
