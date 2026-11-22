from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse

# Paths that don't require a company context. Everything not listed is
# tenant-scoped and gets redirected to the picker when enforcement is
# on and the user has no company resolved.
_TENANT_EXEMPT_PREFIXES = (
    "/accounts/",
    "/healthz/",
    "/oidc/",
    "/api/v1/",
    "/static/",
)

# Auth-flow redirects that HTMX requests must not follow internally.
_HX_AUTH_REDIRECT_PREFIXES = (
    "/accounts/login/",
    "/accounts/company-picker/",
    "/accounts/waiting/",
)


class TenantMiddleware:
    """Resolve request.company and populate the admin-ladder flags.

    Company resolution order:
      1. session["company_id"] (user's explicit choice) — re-validated
         against current membership/employment on every request. A
         stale session is cleared and NOT auto-substituted with another
         company: an open form for the old company must not silently
         write against the new one. Enforcement redirects to the picker.
      2. platform admin → first company
      3. single viable membership AND no session choice yet → that
         company (session auto-set). This branch only fires when the
         user has never explicitly picked a company.
      4. otherwise → None.
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
            request.team = self._resolve_team(request, request.company)
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
            # Session named a company the user can no longer access.
            # Clear and refuse to auto-substitute — the user must
            # explicitly re-pick from the picker.
            request.session.pop("company_id", None)
            return None

        # Session never set. Auto-select when exactly one viable
        # company — the common fresh-login case.
        if len(viable) == 1:
            company = viable[0].company
            request.session["company_id"] = str(company.id)
            return company

        return None

    def _resolve_team(self, request, company):
        """Resolve session["team_id"] to a Team instance (or None).

        Light lookup — no viewability check. select_team validates on
        write; the week endpoint returns an empty roster if the session
        team turns out to be unviewable. A team that doesn't belong to
        the current company is cleared from the session.
        """
        if company is None:
            return None
        session_id = request.session.get("team_id")
        if not session_id:
            return None
        from schedule.models import Team

        try:
            return Team.objects.get(pk=session_id, company=company)
        except Team.DoesNotExist, ValueError:
            request.session.pop("team_id", None)
            return None

    def _is_exempt(self, path):
        if self._admin_prefix and path.startswith(self._admin_prefix):
            return True
        return any(path.startswith(prefix) for prefix in _TENANT_EXEMPT_PREFIXES)


class HTMXLoginRedirectMiddleware:
    """Rewrite HTMX auth-flow redirects to 204 + HX-Redirect.

    Must appear ABOVE TenantMiddleware and EmployeeDeactivationMiddleware
    in MIDDLEWARE — both can short-circuit with a 302 on the request
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
