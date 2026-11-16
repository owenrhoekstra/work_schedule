"""Accounts API endpoints.

Login + CSRF cookie seeding are plain Django views (login is pre-auth,
so Ninja's cookie-based auth/CSRF layer can't run). Companies listing
and selection are Ninja routes with the shared session_auth — post-auth
endpoints where Ninja's session/CSRF model is exactly right.
"""

import json

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth import login as django_login
from django.http import JsonResponse
from django.shortcuts import resolve_url
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST
from ninja import Router

from work_schedule.api.auth import session_auth

from .schemas import (
    CompaniesResponse,
    MeResponse,
    SelectCompanyRequest,
    SelectCompanyResponse,
)

router = Router(tags=["accounts"])


# ---------------------------------------------------------------------------
# Password login (plain Django view)
# ---------------------------------------------------------------------------


@require_POST
@csrf_protect
def login_view(request):
    """Authenticate a user via JSON and establish a session.

    Response shapes:
      {ok: true, redirect_url} on success (200)
      {ok: false, error} on invalid credentials (200)
      {ok: false, error} on missing/invalid fields (422)
      {ok: false, error} on malformed JSON (400)

    `next` param: if present in the payload, validate against allowed
    hosts (same check Django's LoginView uses). Safe local URL →
    honoured as redirect_url. Otherwise → LOGIN_REDIRECT_URL.
    """
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError, UnicodeDecodeError:
        return JsonResponse({"ok": False, "error": "Malformed request."}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"ok": False, "error": "Malformed request."}, status=400)

    username = payload.get("username")
    password = payload.get("password")
    if not isinstance(username, str) or not isinstance(password, str):
        return JsonResponse(
            {"ok": False, "error": "Username and password required."},
            status=422,
        )
    if not username or not password:
        return JsonResponse(
            {"ok": False, "error": "Username and password required."},
            status=422,
        )

    user = authenticate(request, username=username, password=password)
    if user is None:
        return JsonResponse(
            {"ok": False, "error": "Invalid username or password."},
            status=200,
        )

    django_login(request, user)

    redirect_url = resolve_url(settings.LOGIN_REDIRECT_URL)
    next_param = payload.get("next")
    if isinstance(next_param, str) and next_param:
        if url_has_allowed_host_and_scheme(
            url=next_param,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            redirect_url = next_param

    return JsonResponse(
        {"ok": True, "redirect_url": redirect_url},
        status=200,
    )


@require_GET
@ensure_csrf_cookie
def csrf_token_view(request):
    """Set a fresh CSRF cookie. GET-only, idempotent.

    Used by the Vue shell in dev — Vite serves the page directly, so no
    Django render has happened and the csrftoken cookie isn't present.
    In prod the login shell template's {{ csrf_token }} sets the cookie
    during render, so this endpoint isn't called.
    """
    return JsonResponse({"ok": True})


# ---------------------------------------------------------------------------
# Companies (Ninja — post-auth)
# ---------------------------------------------------------------------------


@router.get("/", auth=session_auth, response=CompaniesResponse)
def list_companies(request):
    """List the current user's viable company memberships.

    Scoped to active + still-employed memberships (see
    work_schedule.auth.viable_memberships). Pending memberships are
    excluded — they surface via the acceptance flow, not this list.
    current_company_id reflects the session's chosen company, or null.
    """
    from work_schedule.auth import viable_memberships

    memberships = viable_memberships(request.user)
    return {
        "current_company_id": request.session.get("company_id"),
        "companies": [
            {
                "id": str(m.company.id),
                "name": m.company.name,
                "slug": m.company.slug,
                "role": m.role,
            }
            for m in memberships
        ],
    }


@router.post("/select/", auth=session_auth, response=SelectCompanyResponse)
def select_company(request, payload: SelectCompanyRequest):
    """Set the session company after validating membership.

    Uses viable_memberships so a user cannot switch to a company
    they've been removed from or that has ended employment. Session
    is written only on success.
    """
    from work_schedule.auth import viable_memberships

    company_id = payload.company_id.strip()
    if not company_id:
        return {"ok": False, "error": "company_id required."}

    for m in viable_memberships(request.user):
        if str(m.company_id) == company_id:
            request.session["company_id"] = company_id
            return {"ok": True}

    return {"ok": False, "error": "No access to that company."}


# ---------------------------------------------------------------------------
# Me (Ninja — post-auth)
# ---------------------------------------------------------------------------


me_router = Router(tags=["accounts"])


@me_router.get("/", auth=session_auth, response=MeResponse)
def me(request):
    """Return the session user, viable memberships, and current context.

    `current_company_id` / `current_team_id` mirror request.company /
    request.team as resolved by TenantMiddleware. For platform admins
    this may name a company they have no CompanyMembership at — the
    middleware grants them access to any company, so /me/ reports the
    truth rather than second-guessing. `companies` is still filtered to
    viable_memberships, which means a platform admin can see
    current_company_id that isn't in companies[]. That's intentional:
    companies[] is the switcher list, not "every company this admin can
    reach."

    `companies` mirrors work_schedule.auth.viable_memberships. Pending
    memberships are excluded. `teams` is scoped to viable companies'
    TeamMembership rows (request.team isn't wired yet — the session
    team_id is echoed until the teams UI lands).
    """
    from schedule.models import TeamMembership
    from work_schedule.auth import is_platform_admin, viable_memberships

    memberships = viable_memberships(request.user)

    team_memberships = (
        TeamMembership.objects.filter(
            user=request.user,
            valid_to__isnull=True,
            team__company_id__in={m.company_id for m in memberships},
        )
        .select_related("team")
        .order_by("team__name")
    )
    viable_team_ids = {str(t.team_id) for t in team_memberships}

    session_team = request.session.get("team_id")

    return {
        "id": str(request.user.id),
        "first_name": request.user.first_name,
        "last_name": request.user.last_name,
        "is_platform_admin": is_platform_admin(request.user),
        "permissions": sorted(request.user.get_all_permissions()),
        "current_company_id": (str(request.company.id) if request.company else None),
        "current_team_id": (session_team if session_team in viable_team_ids else None),
        "companies": [
            {
                "id": str(m.company.id),
                "name": m.company.name,
                "slug": m.company.slug,
                "role": m.role,
            }
            for m in memberships
        ],
        "teams": [
            {
                "id": str(t.team.id),
                "name": t.team.name,
                "company_id": str(t.team.company_id),
                "role": t.role,
            }
            for t in team_memberships
        ],
    }
