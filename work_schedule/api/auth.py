"""Session-based authentication for the API.

Django's CsrfViewMiddleware enforces CSRF on every unsafe request
(POST / PUT / PATCH / DELETE) — including Ninja endpoints — as long
as the client sends the X-CSRFToken header, which the Vue SPA
already must for the same-origin HTML/HTMX calls. Ninja's
SessionAuth sits on top and returns `request.user` for authenticated
sessions, `None` for anonymous (Ninja turns that into a 401).

Token auth is a later branch, timed with the Go backend. When that
lands, add a second auth class here and pass `auth=[session_auth,
token_auth]` on the router — no view body changes.
"""

from ninja.security import SessionAuth

session_auth = SessionAuth()