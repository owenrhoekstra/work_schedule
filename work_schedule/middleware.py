from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

# Paths that don't require a company context. Everything not listed is
# tenant-scoped and gets redirected to the picker when enforcement is
# on and the user has no company resolved.
_TENANT_EXEMPT_PREFIXES = (
    "/accounts/",
    "/admin/",
    "/healthz/",
    "/oidc/",
    "/api/v1/",
    "/static/",
)


class TenantMiddleware:
    """Resolve request.company and populate the admin-ladder flags.

    Company resolution order:
      1. session["company_id"] (user's explicit choice)
      2. platform admin → first company (they see all companies)
      3. single active membership → that company (session auto-set)
      4. otherwise → None

    When `settings.TENANT_ENFORCEMENT` is on and a user hits a
    non-exempt path with request.company = None, redirect them to the
    company picker. Enforcement is gated so tests and pre-launch
    deployments can run without company context.
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

            if (
                settings.TENANT_ENFORCEMENT
                and request.company is None
                and not self._is_exempt(request.path)
            ):
                return redirect(reverse("company_picker"))

        return self.get_response(request)

    def _resolve_company(self, request):
        from schedule.models import Company, CompanyMembership
        from work_schedule.auth import is_platform_admin

        session_id = request.session.get("company_id")
        if session_id:
            try:
                return Company.objects.get(pk=session_id)
            except Company.DoesNotExist, ValueError:
                request.session.pop("company_id", None)

        if is_platform_admin(request.user):
            return Company.objects.order_by("id").first()

        memberships = CompanyMembership.objects.filter(
            user=request.user, status="active"
        ).select_related("company")

        if memberships.count() == 1:
            company = memberships.first().company
            request.session["company_id"] = str(company.id)
            return company

        return None

    def _is_exempt(self, path):
        return any(path.startswith(prefix) for prefix in _TENANT_EXEMPT_PREFIXES)


class HTMXLoginRedirectMiddleware:
    """Rewrite HTMX requests' login redirects to 204 + HX-Redirect."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.login_prefix = settings.LOGIN_URL

    def __call__(self, request):
        response = self.get_response(request)

        if (
            request.headers.get("HX-Request") == "true"
            and response.status_code in (301, 302)
            and response.url
            and response.url.startswith(self.login_prefix)
        ):
            redirect_response = HttpResponse(status=204)
            redirect_response["HX-Redirect"] = response.url
            return redirect_response

        return response
