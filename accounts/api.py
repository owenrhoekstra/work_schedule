"""Accounts API endpoints.

JSON login endpoint for the Vue login shell.

Why a plain Django view? Login is pre-auth: the caller has no session
cookie yet, so cookie-based auth classes (which is how django-ninja
enforces CSRF post-1.5) can't run. Plain Django views inherit CSRF
protection from CsrfViewMiddleware without ceremony, which is what
login-CSRF prevention requires. Everything else in the API uses Ninja
+ django_auth, which enforces CSRF automatically.
"""

import json

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth import login as django_login
from django.http import JsonResponse
from django.shortcuts import resolve_url
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST


@require_POST
@csrf_protect
def login_view(request):
    """Authenticate a user via JSON and establish a session.

    Response shapes:
      {ok: true, redirect_url} on success (200)
      {ok: false, error} on invalid credentials (200)
      {ok: false, error} on missing/invalid fields (422)
      {ok: false, error} on malformed JSON (400)

    Generic error message on any auth failure — don't leak lockout
    state vs wrong-password to an unauthenticated caller. Axes still
    logs and locks the account.
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

    return JsonResponse(
        {
            "ok": True,
            "redirect_url": resolve_url(settings.LOGIN_REDIRECT_URL),
        },
        status=200,
    )
