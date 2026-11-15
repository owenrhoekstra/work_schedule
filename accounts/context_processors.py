"""Auth/tenant context flags for templates.

Three flags exposed, plus a legacy `is_management` alias so templates
that haven't migrated yet keep working:

    is_platform_admin  — is_staff, is_superuser, or in Platform Admin
                         group (currently named Management during the
                         commit-2 transition window)
    is_company_admin   — platform admin OR active CompanyMembership
                         with role="admin" at request.company
    is_team_admin      — company admin OR active TeamMembership with
                         role="admin" at request.team (no team context
                         yet, so identical to is_company_admin today)

The ladder is explicit: platform implies company implies team. Each
flag is a superset of the one above it.

`is_management` is the pre-Branch-2 name. It now resolves to
`is_company_admin` (equivalent to `is_management` under the old model,
since Management-group users are platform admins). Removed once every
template uses the explicit flags.
"""

from django.contrib.auth.models import User


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


def user_is_management(request):
    no_flags = {
        "is_management": False,
        "is_platform_admin": False,
        "is_company_admin": False,
        "is_team_admin": False,
    }

    if not request.user.is_authenticated:
        return no_flags

    try:
        is_platform = (
            request.user.is_superuser
            or request.user.is_staff
            or request.user.groups.filter(name="Platform Admin").exists()
            or request.user.groups.filter(name="Management").exists()
        )
    except Exception:
        return no_flags

    is_company = is_platform
    if not is_company:
        company = getattr(request, "company", None)
        if company is not None:
            try:
                from schedule.models import CompanyMembership

                is_company = CompanyMembership.objects.filter(
                    user=request.user,
                    company=company,
                    role="admin",
                    status="active",
                ).exists()
            except Exception:
                is_company = False

    # No team context yet — team admin == company admin.
    is_team = is_company

    return {
        "is_management": is_company,
        "is_platform_admin": is_platform,
        "is_company_admin": is_company,
        "is_team_admin": is_team,
    }
