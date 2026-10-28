# BUGREPORT

Active bugs on the current branch.

## Model

- **Scope:** bugs, not features. UX and feature requests live in
  `docs/UX_BACKLOG.md`.
- **Lifecycle:** cleared at merge. Before merging to main, move any
  remaining items to `docs/ISSUES.md` (or a specific future
  branch's plan if you know where they belong). Then clear this
  file (header stays, content goes).
- **Fixed items:** see `docs/bugs/FIXED.md` (also cleared at merge).
- **Design rationale:** see `docs/design/SESSIONS.md`.

## Branch status

**Current snapshot:** Security sweep, in progress. See
`docs/security/SECURITY_SWEEP.md` for the plan and the full findings
triage (ZAP + `check --deploy` + carried-over items).

---

## Confirmed live bugs

### SEC-001 — CSP header not set

- **Severity:** Medium (defense-in-depth)
- **Symptom:** No `Content-Security-Policy` header on any response.
  ZAP flags this on every page. CSP is a second line of defense that
  blocks external script injection even when an XSS exists elsewhere.
- **Fix direction:** Phase 1 policy with `'unsafe-inline'` — see
  `docs/security/SECURITY_SWEEP.md#csp-plan`. Phase 2 (nonces) is a
  follow-up branch.
- **Target:** This branch.

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

### SEC-004 — Server version header leak

- **Severity:** Low
- **Symptom:** `Server: WSGIServer/0.2 CPython/3.14.0` on every
  response. Reveals exact Python version and WSGI server identity.
- **Fix direction:** Not a Django change. Configure the reverse proxy
  / tunnel to strip or replace the `Server` header (nginx:
  `server_tokens off;` + `more_clear_headers Server;` from
  headers-more module; Caddy: no direct replacement but `header` can
  set/unset; Cloudflare Tunnel: not directly configurable, may need a
  Worker). Document the proxy config in this repo.
- **Target:** This branch (proxy config doc + verification).

### SEC-005 — Production `SECURE_*` settings not set

- **Severity:** Medium
- **Symptom:** `check --deploy` warns W004, W008, W012, W016. Means:
  no HTTPS-only redirect, no HSTS, cookies sent over HTTP if a
  production client ever connects plaintext.
- **Fix direction:** Conditional block in `settings.py`, gated on
  `not DEBUG`. See deployment caveats in
  `docs/security/SECURITY_SWEEP.md`.
- **Target:** This branch.

### SEC-006 — Write-access model inconsistent

- **Severity:** Medium (authorization logic; not a live exploit given
  current permissions model, but blocks a clean future state)
- **Symptom:** Some views are `management_required`-only
  (`employee_details`, `settings_home`, `print_schedule`); others are
  `permission_required`-only (schedule writes). Target state:
  permission-gated everywhere, Management group layered on the
  sensitive ones.
- **Fix direction:** Per `docs/security/SECURITY_SWEEP.md` decision
  point 1. Recommended: Option A (Management layer on destructive +
  tenant-config only).
- **Target:** This branch.

### SEC-007 — Verify password field not re-echoed on signup error

- **Severity:** Low (needs manual verification before assuming it's a
  bug — Django usually omits password values on re-render)
- **Symptom:** ZAP flagged `password1=ZAP` in the `value` attribute of
  the password input on the signup error page. If confirmed, that's a
  minor real bug (password in HTML source). If ZAP misread the
  `initial-value` attribute, it's a false positive.
- **Fix direction:** Manually submit an invalid signup and inspect the
  re-rendered password input. If it has a `value` attribute with the
  submitted password, override the field rendering.
- **Target:** This branch (verification + fix if confirmed).
