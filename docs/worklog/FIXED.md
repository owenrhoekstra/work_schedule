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