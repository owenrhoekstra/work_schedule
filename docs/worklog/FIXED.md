# FIXED

Bugs fixed on the current branch, newest at the bottom.

## Model

- **Scope:** bugs and technical fixes, not features. See
  `docs/design/SESSIONS.md` for the _why_ behind each one.
- **Lifecycle:** cleared at merge. Before merging to main, extract
  each entry's "Follow-up" and "Known limitation" notes into
  `docs/ISSUES.md` with a one-line origin breadcrumb. Then clear
  this file (header stays, content goes).
- **Permanent archive:** the git commit log. FIXED entries exist to
  keep the current branch's work visible at a glance; they don't
  need to survive past merge.

---

### SEC-002 — CSRF token leaked in HTMX preview GET query string

- **Severity:** Low (informational only; token is per-session and
  endpoint is read-only)
- **Symptom:** `hx-include="closest form"` on the cycle/week pickers
  serializes the form including the hidden `csrfmiddlewaretoken` field
  into the GET URL for `pattern_form_preview`. The token appears in
  proxy logs, access logs, and Referer headers downstream.
- **Fix direction:** Use `hx-params="not csrfmiddlewaretoken"` on the
  preview-triggering elements, or switch the preview endpoint to POST
  and use the existing `X-CSRFToken` header path.
- **Target:** This branch.
- Fixed in commit 2eba2ae8017e57454eb242f131cd73ae2b83901f

### SEC-003 — Permissive CORS header on static assets

- **Severity:** Low (no sensitive data in static files)
- **Symptom:** `/static/css/dist/styles.css` returns
  `Access-Control-Allow-Origin: *`. ZAP flags "Cross-Domain
  Misconfiguration." No authenticated data is exposed, but a wildcard
  CORS header on static assets is unnecessary.
- **Fix direction:** Identify the source — likely WhiteNoise,
  django-cors-headers if installed, or a proxy config. Remove the
  header or restrict to the actual origin.
- **Target:** This branch.
- Fixed in commit fb9bbc69b5e0d66a1cdf1bd258d8561800d09df0

### SEC-005 — Production `SECURE_*` settings

- **Verified, no code change.** `settings.py` already has the full
  `SECURE_*` block gated on `DJANGO_SECURE`: SSL redirect, HSTS
  (31536000, includeSubDomains, preload on prod only),
  `SECURE_PROXY_SSL_HEADER` (X-Forwarded-Proto), secure session +
  CSRF cookies, `/healthz/` redirect exempt. Both staging and prod
  set `DJANGO_SECURE=True`.
- **Verification:** `DJANGO_DEBUG=false DJANGO_SECURE=true manage.py
check --deploy` — expect clean (re-run in final sweep).
- **Decision:** The sweep doc originally said "gate on `not DEBUG`";
  the code gates on `DJANGO_SECURE`. Keeping the env var switch
  (documented in README). No system-check added — staging and prod
  are both confirmed correct, and a warning on `DEBUG=False, SECURE=False`
  isn't worth maintaining for a two-environment deploy.
- **CSP Phase 1 (SEC-001)** is **not fixed** — deferred to a follow-up
  branch. Tracked in `SECURITY_SWEEP.md` under out-of-scope.

### SEC-004 — Server version header leak

- **Verified, no code change.** Cloudflare Tunnel replaces the
  upstream `Server: WSGIServer/0.2 CPython/3.14.0` header with
  `Server: cloudflare` on the way out. Confirmed against prod:
  `curl -sI https://work-schedule.principiasystems.ca | grep -i '^server:'`
  returns `server: cloudflare`.
- **Decision:** No proxy config needed. If a future deploy topology
  bypasses Cloudflare (direct nginx, VPS direct serve), this reopens —
  the fix would then be `proxy_hide_header Server;` in nginx or
  `header { -Server }` in Caddy. Noting for the record; no action now.

### SEC-007 — Password field echoed on signup error

- **Verified false positive.** ZAP flagged `password1=ZAP` in the
  signup error page input. Code analysis confirms no echo:
  - `SignUpForm` inherits Django's `UserCreationForm`, whose
    `password1` / `password2` are `PasswordInput` widgets with
    `render_value` at its default (`False`).
  - `SignUpForm.__init__` only updates `attrs["class"]`; never
    touches `render_value`.
  - `PasswordInput.get_context()` sets `value = None` when
    `render_value` is False — the rendered HTML has no `value`
    attribute.
  - `registration/signup.html` uses `{{ form.password1 }}` (standard
    rendering), no manual `value=` attribute.
- **Root cause of the ZAP finding:** ZAP reading its own request
  payload, not the response. Matches the "may be a false positive"
  hypothesis in the original sweep triage.
- **Target: verified no-op.** Automated test for this deferred to the
  `accounts/` test-layout branch (per SECURITY_SWEEP.md out-of-scope).
