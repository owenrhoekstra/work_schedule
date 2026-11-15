"""Auth/tenant context flags for templates.

Reads the flags TenantMiddleware already computed on the request. One
DB query per request (in the middleware) instead of one per template
render.

Falls back to computing the flags directly when the request didn't
come through TenantMiddleware — tests using RequestFactory, error
pages, and any future code path that bypasses the middleware. The
fallback is one extra query only in those cases; production requests
still read the pre-computed flags.
"""

from django.contrib.auth.models import User

_MISSING = object()


def pending_accounts(request):
    if not request.user.is_authenticated or not request.user.has_perm(
        "schedule.add_employee"
    ):
        return {}
    try:
        count = (
            User.objects.filter(is_active=False, employees__is_active=True)
            .distinct()
            .count()
        )
    except Exception:
        return {}
    return {"pending_accounts_count": count}


def _flag(request, name):
    """Return request.<name> if set, else compute it via the auth helpers.

    Set by TenantMiddleware on every real request. Missing means the
    request bypassed the middleware (RequestFactory in tests, error
    pages, etc.) — compute on the spot so templates still get a
    correct answer.
    """
    value = getattr(request, name, _MISSING)
    if value is not _MISSING:
        return value

    if not request.user.is_authenticated:
        return False

    from work_schedule.auth import (
        is_company_admin,
        is_platform_admin,
        is_team_admin,
    )

    company = getattr(request, "company", None)
    team = getattr(request, "team", None)

    if name == "is_platform_admin":
        return is_platform_admin(request.user)
    if name == "is_company_admin":
        return is_company_admin(request.user, company)
    if name == "is_team_admin":
        return is_team_admin(request.user, team, company)
    return False


def user_is_management(request):
    return {
        # Legacy alias — resolves to is_company_admin. Removed once
        # every template uses the explicit flags.
        "is_management": _flag(request, "is_company_admin"),
        "is_platform_admin": _flag(request, "is_platform_admin"),
        "is_company_admin": _flag(request, "is_company_admin"),
        "is_team_admin": _flag(request, "is_team_admin"),
    }


def oidc_enabled(request):
    from django.conf import settings

    return {"oidc_enabled": getattr(settings, "OIDC_ENABLED", False)}
