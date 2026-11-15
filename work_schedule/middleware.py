from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse

# Paths that don't require a company context. Everything not listed is
# tenant-scoped and gets redirected to the picker when enforcement is
# on and the user has no company resolved.
#
# The admin URL is dynamically prepended to this list (see
# TenantMiddleware.__init__) so the exempt list always matches whatever
# URL the project configured, not a hardcoded "/admin/".
_TENANT_EXEMPT_PREFIXES = (
    "/accounts/",
    "/healthz/",
    "/oidc/",
    "/api/v1/",
    "/static/",
)


# Auth-flow redirects that HTMX requests must not follow internally —
# HTMX follows a 302, receives the destination HTML (200), and swaps
# it into the fragment target, producing a nested-page rendering bug.
# Any 302 to one of these becomes 204 + HX-Redirect instead, so the
# browser does a full-page navigation.
_HX_AUTH_REDIRECT_PREFIXES = (
    "/accounts/login/",
    "/accounts/company-picker/",
    "/accounts/waiting/",
)


class TenantMiddleware:
    """Resolve request.company and populate the admin-ladder flags.

    Company resolution order:
      1. session["company_id"] (user's explicit choice) — re-validated
         against current membership/employment on every request
      2. platform admin → first company (they see all companies)
      3. single viable membership → that company (session auto-set)
      4. otherwise → None

    "Viable" means the membership's status is active AND (if an
    Employee row exists for this user at that company) they haven't
    passed their last_day. See work_schedule.auth.viable_memberships.

    When `settings.TENANT_ENFORCEMENT` is on and a user hits a
    non-exempt path with request.company = None, redirect them to the
    company picker.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        try:
            self._admin_prefix = reverse("admin:index")
        except Exception:
            self._admin_prefix = None

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
        from schedule.models import Company
        from work_schedule.auth import is_platform_admin, viable_memberships

        if is_platform_admin(request.user):
            session_id = request.session.get("company_id")
            if session_id:
                try:
                    return Company.objects.get(pk=session_id)
                except Company.DoesNotExist, ValueError:
                    request.session.pop("company_id", None)
            return Company.objects.order_by("id").first()

        viable = viable_memberships(request.user)
        viable_ids = {str(m.company_id) for m in viable}

        session_id = request.session.get("company_id")
        if session_id:
            if session_id in viable_ids:
                for m in viable:
                    if str(m.company_id) == session_id:
                        return m.company
            request.session.pop("company_id", None)

        if len(viable) == 1:
            company = viable[0].company
            request.session["company_id"] = str(company.id)
            return company

        return None

    def _is_exempt(self, path):
        if self._admin_prefix and path.startswith(self._admin_prefix):
            return True
        return any(path.startswith(prefix) for prefix in _TENANT_EXEMPT_PREFIXES)


class HTMXLoginRedirectMiddleware:
    """Rewrite HTMX auth-flow redirects to 204 + HX-Redirect.

    HTMX follows 302s, receives the destination HTML with a 200, and
    swaps it into the fragment target — the user ends up with a login
    page (or company picker, or waiting page) rendered inside a
    schedule cell. Catch any 302 to an auth-flow URL and convert it
    to a 204 with HX-Redirect, which tells HTMX to do a full-page
    navigation instead.

    Must appear ABOVE TenantMiddleware and EmployeeDeactivationMiddleware
    in MIDDLEWARE. Both can short-circuit with a 302 on the request
    phase; if this middleware is below them, its response phase never
    runs and the 302 escapes to HTMX.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if (
            request.headers.get("HX-Request") == "true"
            and response.status_code in (301, 302)
            and response.url
            and any(response.url.startswith(p) for p in _HX_AUTH_REDIRECT_PREFIXES)
        ):
            redirect_response = HttpResponse(status=204)
            redirect_response["HX-Redirect"] = response.url
            return redirect_response

        return response
