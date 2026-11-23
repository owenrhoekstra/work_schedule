"""Tenant authorization primitives.

The admin ladder: platform > company > team. Each check is a superset
of the level below it, so a platform admin passes every gate, a
company admin passes company and team gates, and a team admin passes
only team gates (for teams they administer).

Consumed by:
- `work_schedule.middleware.TenantMiddleware` — populates
  request.is_platform_admin / is_company_admin / is_team_admin once
  per request.
- `work_schedule.views` — decorators that read request flags.
- `accounts.context_processors` — exposes the flags to templates.

During the Branch 2 transition both "Platform Admin" and "Management"
group names are accepted, so pre-rename databases keep working.

`is_team_admin(user, team=None, company=X)` degrades to a company-admin
check when no team is in scope — the correct behavior while the UI has
no team picker. When teams land, callers pass request.team and a team
admin of a different team is correctly denied.
"""

from functools import wraps

from django.core.exceptions import PermissionDenied


def is_platform_admin(user):
    """True if the user is a platform-level admin.

    is_staff / is_superuser, or membership in the Platform Admin group
    (formerly Management). Independent of any company context.
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    return user.groups.filter(name__in=["Platform Admin", "Management"]).exists()


def is_company_admin(user, company):
    """True if the user is an admin of `company`.

    Platform admins pass (ladder). Otherwise requires an active
    CompanyMembership with role="admin" at that company.
    """
    if not user.is_authenticated:
        return False
    if is_platform_admin(user):
        return True
    if company is None:
        return False
    from schedule.models import CompanyMembership

    return CompanyMembership.objects.filter(
        user=user, company=company, role="admin", status="active"
    ).exists()


def is_team_admin(user, team, company):
    """True if the user is an admin of `team` (or higher in the ladder).

    Company admins pass (ladder). Otherwise requires an active
    TeamMembership with role="admin" on that specific team. When
    `team` is None — no team in scope — degrades to a company-admin
    check: the caller is asking "is this user an admin of anything in
    the current context," and the answer is "yes if they're a company
    admin, no otherwise."
    """
    if is_company_admin(user, company):
        return True
    if team is None or not user.is_authenticated:
        return False
    from schedule.models import TeamMembership

    return TeamMembership.objects.filter(
        user=user, team=team, role="admin", valid_to__isnull=True
    ).exists()


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------


def platform_admin_required(view):
    """Require platform admin (is_staff or Platform Admin group)."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated and is_platform_admin(request.user):
            return view(request, *args, **kwargs)
        raise PermissionDenied

    return wrapper


def company_admin_required(view):
    """Require company admin (or platform admin). Reads request.company."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied
        company = getattr(request, "company", None)
        if is_company_admin(request.user, company):
            return view(request, *args, **kwargs)
        raise PermissionDenied

    return wrapper


def team_admin_required(view):
    """Require team admin (or company admin, or platform admin).

    Reads request.company and request.team. When request.team is None
    (current state — no team UI), this behaves identically to
    company_admin_required.
    """

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied
        company = getattr(request, "company", None)
        team = getattr(request, "team", None)
        if is_team_admin(request.user, team, company):
            return view(request, *args, **kwargs)
        raise PermissionDenied

    return wrapper


def any_admin_required(view):
    """Alias for team_admin_required.

    'Any admin in the current context' is equivalent to 'team admin of
    the current team, or company admin, or platform admin.' Kept as a
    named decorator for readability at call sites that don't care which
    level of admin acts, only that an admin does.
    """
    return team_admin_required(view)


def viable_memberships(user):
    """Active CompanyMemberships where the user is still employed.

    A membership is "viable" when its status is "active" AND (if an
    Employee row exists for this user at that company) the employee
    hasn't passed their `last_day`. Member-only users — people granted
    access without being on the schedule — are viable regardless.

    Used by TenantMiddleware._resolve_company (session-path
    revalidation and auto-select) and accounts.company_picker (the
    picker list). Centralizing here keeps those two callers from
    drifting apart as enforcement grows.
    """
    from django.utils import timezone

    from schedule.models import CompanyMembership

    today = timezone.localdate()
    viable = []
    for m in CompanyMembership.objects.filter(
        user=user, status="active"
    ).select_related("company"):
        employee = user.employees.filter(company=m.company).first()
        if employee is None:
            viable.append(m)
        elif employee.last_day is None or employee.last_day >= today:
            viable.append(m)
    return viable
