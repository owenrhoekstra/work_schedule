# BUGREPORT

Active bugs on the current branch.

## Model

- **Scope:** bugs, not features. UX and feature requests live in
  `docs/UX_BACKLOG.md`.
- **Lifecycle:** cleared at merge. Before merging to main, move any
  remaining items to `docs/ISSUES.md` (or a specific future
  branch's plan if you know where they belong). Then clear this
  file (header stays, content goes).
- **Fixed items:** see `docs/worklog/FIXED.md` (also cleared at merge).
- **Design rationale:** see `docs/design/SESSIONS.md`.

## Branch status

**Current snapshot:** Security sweep, in progress. SEC-002, SEC-003,
SEC-004, SEC-005, and SEC-007 resolved (SEC-004 and SEC-007 verified
as no-ops — no code change). SEC-006 backend + UI complete, tests
passing. CSP deferred. See `docs/security/SECURITY_SWEEP.md`.

---

## Confirmed live bugs

### SEC-006 — Write-access model inconsistent

- **Severity:** Medium (authorization logic; not a live exploit given
  current permissions model, but blocks a clean future state)
- **Symptom:** Some views are `management_required`-only
  (`employee_details`, `settings_home`, `print_schedule`, `qr_code`
  has neither); others are `permission_required`-only (schedule
  writes). Target state: permission-gated everywhere, Management
  group layered on writes/destructive/tenant-config, UI AND-gated to
  match.
- **Fix direction:** Per `docs/security/SECURITY_SWEEP.md` views
  table. Backend: add decorators. UI: `{% if is_management and
  perms.schedule.X %}`.
- **Target:** This branch.
