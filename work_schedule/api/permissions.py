"""Ninja permission classes mirroring the decorators in work_schedule.auth.

Class name matches the decorator name in CamelCase (company_admin_required
→ CompanyAdmin). Raising HttpError from authenticate() propagates the
status; returning None means "not authenticated" and becomes a 401.

Every endpoint gated by a decorator in the HTML tree uses the matching
class here. HasPerm combines the admin gate with the permission check
for the common "admin + perm" case; MemberWithPerm covers the "any
authenticated member holding the perm" case for read endpoints.
"""

from ninja.errors import HttpError
from ninja.security import SessionAuth

from work_schedule.auth import (
    is_company_admin,
    is_platform_admin,
    is_team_admin,
)


class PlatformAdmin(SessionAuth):
    """`is_staff` or Platform Admin group. Matches platform_admin_required."""

    def authenticate(self, request, key):
        user = super().authenticate(request, key)
        if user is None or not is_platform_admin(user):
            return None
        return user


class CompanyAdmin(SessionAuth):
    """Active company admin at request.company. Matches company_admin_required."""

    def authenticate(self, request, key):
        user = super().authenticate(request, key)
        if user is None:
            return None
        company = request.company
        if company is None:
            raise HttpError(400, "No company in context.")
        if not is_company_admin(user, company):
            raise HttpError(403, "Forbidden.")
        return user


class TeamAdmin(SessionAuth):
    """Active team admin at request.team (or company admin). Matches
    team_admin_required. Degrades to a company-admin check when
    request.team is None — same behavior as the decorator.
    """

    def authenticate(self, request, key):
        user = super().authenticate(request, key)
        if user is None:
            return None
        company = request.company
        if company is None:
            raise HttpError(400, "No company in context.")
        if not is_team_admin(user, request.team, company):
            raise HttpError(403, "Forbidden.")
        return user


class AnyAdmin(SessionAuth):
    """Company admin OR team admin. Matches any_admin_required.

    any_admin_required is an alias for team_admin_required in
    work_schedule.auth, and is_team_admin already degrades to a
    company-admin check at the current context. So the body is
    identical to TeamAdmin — kept as a separate class name so endpoint
    intent reads clearly at call sites.
    """

    def authenticate(self, request, key):
        user = super().authenticate(request, key)
        if user is None:
            return None
        company = request.company
        if company is None:
            raise HttpError(400, "No company in context.")
        if not is_team_admin(user, request.team, company):
            raise HttpError(403, "Forbidden.")
        return user


class EmployeeRequired(SessionAuth):
    """Employee row at request.company. Matches employee_required."""

    def authenticate(self, request, key):
        user = super().authenticate(request, key)
        if user is None:
            return None
        company = request.company
        if company is None:
            raise HttpError(400, "No company in context.")
        if not user.employees.filter(company=company).exists():
            raise HttpError(403, "Forbidden.")
        return user


class HasPerm(SessionAuth):
    """Company admin + per-permission check.

    - HasPerm()                    → any company admin
    - HasPerm("schedule.X")        → company admin holding perm X
    - HasPerm(*DAY_OVERRIDE_PERMS) → company admin holding all listed perms

    Endpoints whose perm depends on the payload (set_override's off/save
    split) use HasPerm() for the admin gate and check the action perm
    in the body — matching the HTML view's structure. No class-based
    system can see the parsed payload before authenticate runs.
    """

    def __init__(self, *perms: str):
        # SessionAuth → APIKeyCookie.__init__ sets self.csrf. Skipping
        # super() drops that attribute and _get_key crashes before
        # authenticate() even runs.
        super().__init__()
        self.perms = perms

    def authenticate(self, request, key):
        user = super().authenticate(request, key)
        if user is None:
            return None
        company = request.company
        if company is None:
            raise HttpError(400, "No company in context.")
        if not is_company_admin(user, company):
            raise HttpError(403, "Forbidden.")
        if not all(user.has_perm(p) for p in self.perms):
            raise HttpError(403, "Forbidden.")
        return user


class MemberWithPerm(SessionAuth):
    """Authenticated user holding the given perms. No admin required.

    Matches the admin=False branch of the old authorize() helper. For
    read endpoints where any member with the perm may pass — e.g.
    /week/ (a plain employee with view_shift reads their own scope).
    Company must exist in context.
    """

    def __init__(self, *perms: str):
        super().__init__()
        self.perms = perms

    def authenticate(self, request, key):
        user = super().authenticate(request, key)
        if user is None:
            return None
        if request.company is None:
            raise HttpError(400, "No company in context.")
        if not all(user.has_perm(p) for p in self.perms):
            raise HttpError(403, "Forbidden.")
        return user
