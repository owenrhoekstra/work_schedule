"""Accounts API endpoints.

JSON login endpoint for the Vue login shell, and a CSRF-cookie seeding
view for dev mode.

Why plain Django views and not Ninja? Login is pre-auth: the caller
has no session cookie yet, so cookie-based auth classes (django-ninja's
CSRF enforcement mechanism post-1.5) can't run. Plain Django views
inherit CSRF protection from CsrfViewMiddleware without ceremony.
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


@require_POST
@csrf_protect
def login_view(request):
    """Authenticate a user via JSON and establish a session.

    Response shapes:
      {ok: true, redirect_url} on success (200)
      {ok: false, error} on invalid credentials (200)
      {ok: false, error} on missing/invalid fields (422)
      {ok: false, error} on malformed JSON (400)

    `next` param: if the payload carries a `next` string, validate it
    against allowed hosts (same check Django's LoginView uses). Safe
    local URL → honoured as redirect_url. Otherwise → fall back to
    LOGIN_REDIRECT_URL. This lets a user who was bounced to login from
    an expired session land back on the page they were on.
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


@require_GET
def list_companies_view(request):
    """List the current user's active company memberships.

    Response:
      {
        "current_company_id": "<uuid>" | null,
        "companies": [
          {"id": "<uuid>", "name": "...", "slug": "...", "role": "admin"|"member"}
        ]
      }

    Scoped to viable memberships (active + still-employed, per
    work_schedule.auth.viable_memberships). Pending memberships are
    excluded — they surface via the acceptance flow, not this list.

    401 for unauthenticated requests. Zero memberships is a valid
    response (empty list); the client routes accordingly.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required"}, status=401)

    from work_schedule.auth import viable_memberships

    memberships = viable_memberships(request.user)
    current_id = request.session.get("company_id")

    return JsonResponse(
        {
            "current_company_id": current_id,
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
    )


@require_POST
@csrf_protect
def select_company_view(request):
    """Set the session company after validating membership.

    Body: {"company_id": "<uuid>"}

    Response shapes:
      {"ok": true} on success (200)
      {"ok": false, "error": "..."} on missing/invalid company_id (422)
      {"ok": false, "error": "..."} on no-access (200)
      401 for unauthenticated requests

    Validation mirrors the HTML company_picker view: the target must
    be in viable_memberships(request.user). Session is set only on
    success.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required"}, status=401)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError, UnicodeDecodeError:
        return JsonResponse({"ok": False, "error": "Malformed request."}, status=400)

    company_id = payload.get("company_id") if isinstance(payload, dict) else None
    if not isinstance(company_id, str) or not company_id:
        return JsonResponse({"ok": False, "error": "company_id required."}, status=422)

    from work_schedule.auth import viable_memberships

    for m in viable_memberships(request.user):
        if str(m.company_id) == company_id:
            request.session["company_id"] = company_id
            return JsonResponse({"ok": True})

    return JsonResponse({"ok": False, "error": "No access to that company."})
