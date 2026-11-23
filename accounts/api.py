"""Accounts API endpoints.

Login + CSRF cookie seeding are plain Django views (login is pre-auth,
so Ninja's cookie-based auth/CSRF layer can't run). Companies listing
and selection are Ninja routes with the shared session_auth — post-auth
endpoints where Ninja's session/CSRF model is exactly right.
"""

import json
from uuid import UUID

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
from work_schedule.auth import is_company_admin, is_team_admin

from .schemas import (
    CompaniesResponse,
    MeResponse,
    SelectCompanyRequest,
    SelectCompanyResponse,
    SelectTeamRequest,
    SelectTeamResponse,
)

router = Router(tags=["accounts"])
teams_router = Router(tags=["accounts"])

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
    from work_schedule.auth import viable_memberships

    company_id = payload.company_id.strip()
    if not company_id:
        return {"ok": False, "error": "company_id required."}

    for m in viable_memberships(request.user):
        if str(m.company_id) == company_id:
            # Only clear team_id when switching to a DIFFERENT company.
            # Re-selecting the same company preserves the team selection.

            print(
                f"[select_company] session_company={request.session.get('company_id')!r} "
                f"payload_company={company_id!r} "
                f"equal={request.session.get('company_id') == company_id} "
                f"session_team={request.session.get('team_id')!r}"
            )

            if request.session.get("company_id") != company_id:
                request.session.pop("team_id", None)
            request.session["company_id"] = company_id
            return {"ok": True}

    return {"ok": False, "error": "No access to that company."}


@teams_router.post("/select/", auth=session_auth, response=SelectTeamResponse)
def select_team(request, payload: SelectTeamRequest):
    """Set or clear the session team.

    Team must be viewable as team scope: admin role in TeamMembership,
    or member of a team whose allow_member_view_all is true (with the
    user's Employee row showing show_team_schedules). None/empty
    clears the selection and the roster falls back to the union of all
    viewable teams.

    Reads request.company from TenantMiddleware — team must belong to
    the currently-selected company.
    """
    from schedule.selectors import viewable_team_ids

    if payload.team_id is None or payload.team_id == "":
        request.session.pop("team_id", None)
        return {"ok": True}

    company = request.company
    if company is None:
        return {"ok": False, "error": "No company in context."}

    try:
        team_uuid = UUID(payload.team_id)
    except ValueError, TypeError:
        return {"ok": False, "error": "Invalid team ID."}

    if team_uuid not in viewable_team_ids(request.user, company):
        return {"ok": False, "error": "No access to that team."}

    request.session["team_id"] = str(team_uuid)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Me (Ninja — post-auth)
# ---------------------------------------------------------------------------


me_router = Router(tags=["accounts"])


@me_router.get("/", auth=session_auth, response=MeResponse)
def me(request):
    from schedule.models import TeamMembership
    from work_schedule.auth import is_platform_admin, viable_memberships

    memberships = viable_memberships(request.user)

    from schedule.selectors import available_scopes_for, viewable_team_ids

    if request.company is not None:
        allowed_ids = viewable_team_ids(request.user, request.company)
        team_memberships = (
            TeamMembership.objects.filter(
                user=request.user,
                valid_to__isnull=True,
                team__company=request.company,
                team_id__in=allowed_ids,
            )
            .select_related("team")
            .order_by("team__name")
        )
    else:
        team_memberships = TeamMembership.objects.none()
    viable_team_ids = {str(t.team_id) for t in team_memberships}

    session_team = request.session.get("team_id")

    first_name = request.user.first_name or request.user.get_username()

    return {
        "id": str(request.user.id),
        "first_name": first_name,
        "last_name": request.user.last_name,
        "is_platform_admin": is_platform_admin(request.user),
        "is_company_admin": [
            {
                "status": is_company_admin(request.user, m.company.id),
                "company_id": str(m.company.id),
            }
            for m in memberships
        ],
        "is_team_admin": [
            {
                "status": is_team_admin(request.user, t.team.id, t.team.company_id),
                "company_id": str(t.team.company_id),
                "team_id": str(t.team.id),
            }
            for t in team_memberships
        ],
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
        "available_scopes": (
            available_scopes_for(request.company, request.user)
            if request.company
            else []
        ),
    }
