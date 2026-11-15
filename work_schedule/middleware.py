"""Project-level middleware. App-agnostic cross-cutting behavior."""

from django.conf import settings
from django.http import HttpResponse


class TenantMiddleware:
    """Populate request.company and request.team from the session.

    Session choice wins. Superusers default to the first company.
    Regular users with exactly one active CompanyMembership are
    auto-assigned (session written). Users with 2+ memberships stay
    None for now — commit 3 adds the picker redirect.

    Branch 2, commit 1: no redirects. Views fall back via
    _current_company to the first company when request.company is
    None, preserving single-tenant behavior for existing tests.
    Commit 3 enforces redirects on non-whitelisted paths.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.company = None
        request.team = None

        if not request.user.is_authenticated:
            return self.get_response(request)

        request.company = self._resolve_company(request)
        # request.team stays None; team resolution lands in a later branch.

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
