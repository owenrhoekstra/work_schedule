# FIXED

Bugs fixed on the current branch, newest at the bottom.

## Model

- **Scope:** bugs and technical fixes, not features. See
  `docs/design/SESSIONS.md` for the *why* behind each one.
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