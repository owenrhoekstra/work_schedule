"""Ninja permission classes.

These mirror the decorators used on HTML views. Class name matches
the decorator name in CamelCase (`company_admin_required` →
`CompanyAdmin`). Branch 0 ships `PlatformAdmin` (functional) plus
placeholders for the tenant-aware permissions. The placeholders
inherit from `SessionAuth` — they gate on authentication only until
Branch 2 wires `request.company` into the request lifecycle, at
which point each placeholder gains its real check.
"""

from ninja.security import SessionAuth


class PlatformAdmin(SessionAuth):
    """`is_staff` user. Matches `platform_admin_required` on views.

    Gates platform-only endpoints (docs, future tooling). Django
    admin is unaffected — it has its own gate.
    """

    def authenticate(self, request, key):
        user = super().authenticate(request, key)
        if user is None or not user.is_staff:
            return None
        return user


class CompanyAdmin(SessionAuth):
    """Placeholder — will require an active CompanyMembership at
    `request.company` in Branch 2.
    """


class TeamAdmin(SessionAuth):
    """Placeholder — will require an active TeamMembership at
    `request.team` (plus an active CompanyMembership) in Branch 2.
    """


class AnyAdmin(SessionAuth):
    """Placeholder — company admin OR team admin. The workhorse for
    most write endpoints once Branch 2 lands.
    """


class EmployeeRequired(SessionAuth):
    """Placeholder — will require an Employee record at
    `request.company` in Branch 2.
    """