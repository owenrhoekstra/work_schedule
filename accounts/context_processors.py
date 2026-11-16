"""Auth/tenant context flags for templates.

Reads the flags TenantMiddleware already computed on the request. One
DB query per request (in the middleware) instead of one per template
render.

Falls back to computing the flags directly when the request didn't
come through TenantMiddleware — tests using RequestFactory, error
pages, and any future code path that bypasses the middleware.
"""

from django.conf import settings

_MISSING = object()


def pending_accounts(request):
    """Pending membership count for the current company.

    Uses request.company (set by TenantMiddleware). Returns {} if the
    user lacks the underlying permission, is anonymous, or has no
    company context. The count drives the "N Pending" badge in the
    navigation bar — it should reflect the manager's own queue, not
    a global count.
    """
    if not request.user.is_authenticated:
        return {}
    if not request.user.has_perm("schedule.add_employee"):
        return {}

    company = getattr(request, "company", None)
    if company is None:
        return {}

    try:
        from schedule.models import CompanyMembership

        count = CompanyMembership.objects.filter(
            company=company, status="pending"
        ).count()
    except Exception:
        return {}

    return {"pending_accounts_count": count}


def oidc_enabled(request):
    """True when Zitadel OIDC credentials are configured.

    Read by the login shell template to decide whether to show the
    "Sign in with Zitadel" button. Cheap — just settings lookup, no DB.
    """
    return {"oidc_enabled": getattr(settings, "OIDC_ENABLED", False)}


def _flag(request, name):
    """Return request.<name> if set, else compute it via the auth helpers."""
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


def auth_flags(request):
    """Admin-ladder template flags.

    Returns the three rungs of the per-request admin ladder. Templates
    AND-gate UI against their view's permission_required and
    admin-required decorators using these.
    """
    return {
        "is_platform_admin": _flag(request, "is_platform_admin"),
        "is_company_admin": _flag(request, "is_company_admin"),
        "is_team_admin": _flag(request, "is_team_admin"),
    }
