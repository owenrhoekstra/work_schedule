"""Project-level middleware. App-agnostic cross-cutting behavior."""

from django.conf import settings
from django.http import HttpResponse


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