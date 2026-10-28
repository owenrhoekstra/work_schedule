# Security sweep — branch plan

## Status

Decisions confirmed. Ready to start.

- Write-access model: `permission_required` on every view;
  `management_required` layered on writes, destructive actions, and
  tenant config. UI elements gated on `is_management`.
- CSP: Phase 1 with `'unsafe-inline'`. Nonces deferred to a
  follow-up branch.

## Why this branch exists

Session 9's QA pass surfaced hardening items that don't belong in a
feature branch. ZAP against dev, `check --deploy` against current
settings, and the write-access item carried from `ISSUES.md` all
converge here.

Scope discipline: **good not perfect.** Fix the real risks, close the
real inconsistencies, defer the deep work (nonces, HSTS preload,
dependency scanning) to their own branches.

## In scope

- `SECURE_*` settings conditional on `not DEBUG` (SEC-005)
- CSP Phase 1 middleware + policy (SEC-001)
- Write-access model refactor — backend and UI (SEC-006)
- CSRF token exclusion from HTMX preview GET query string (SEC-002)
- CORS header audit on static assets (SEC-003)
- Server header strip at proxy (SEC-004) — proxy-side, doc the config
- Manual verification of password-echo on signup error (SEC-007)

## Out of scope (future branches)

- CSP Phase 2: nonces, drop `unsafe-inline`
- HSTS preload (`preload` needs 3+ months of stable HTTPS)
- Dependency vulnerability scanning
- Audit logging / SIEM
- Rate limiting beyond `django-axes`
- Origin checking changes (modern Django defaults are fine)

## Findings triage

### `check --deploy` warnings — all SEC-005

| Code | Setting | Target |
|---|---|---|
| W004 | `SECURE_HSTS_SECONDS` | 3600 (ramp to 31536000 after stable HTTPS) |
| W008 | `SECURE_SSL_REDIRECT` | True (gated on `not DEBUG`) |
| W012 | `SESSION_COOKIE_SECURE` | True (gated on `not DEBUG`) |
| W016 | `CSRF_COOKIE_SECURE` | True (gated on `not DEBUG`) |
| W018 | `DEBUG=True` | Dev-only. Verify prod via `DJANGO_DEBUG=false check --deploy`. |

### ZAP — false positives (mark in ZAP, no code change)

- **SQL Injection on `/accounts/login/`** — evidence shows a 429
  lockout response; ZAP flagged SQLi because two 429 pages differed
  (dynamic CSRF token in the body). Django ORM auth is parameterized.
  Suppress in ZAP context.
- **Timestamp Disclosure (`?v=...`)** — WhiteNoise cache-buster.
- **Suspicious Comments** — ZAP's `USER` pattern matched "user" in a
  JS comment.
- **Cookie No HttpOnly Flag (csrftoken)** — intentional. HTMX reads
  the CSRF cookie and sets `X-CSRFToken`; HttpOnly would break it.
- **Authentication Request / Session Management / Tech Detected /
  Modern Web App / User Agent Fuzzer / Re-examine Cache-control** —
  informational.

### ZAP — real, actionable

| SEC | Alert | Fix |
|---|---|---|
| SEC-001 | CSP Header Not Set | Middleware + Phase 1 policy |
| SEC-002 | Sensitive Info in URL (`csrfmiddlewaretoken`) | HTMX `hx-params` exclusion |
| SEC-003 | Cross-Domain Misconfiguration (`ACAO: *`) | Remove CORS header from static |
| SEC-004 | Server Leaks Version (`WSGIServer/...`) | Strip at proxy |
| SEC-005 | `check --deploy` warnings | Conditional `SECURE_*` |
| SEC-006 | Write-access model inconsistency | Permission + Management per policy |
| SEC-007 | Password field echo (unverified) | Manual check, fix if real |

## View + UI gating

### Views — permission layer

Every view must have a `permission_required` decorator. Two views
stay permission-only; the rest also get `management_required` per the
policy (writes, destructive, tenant config).

| View | `permission_required` | `management_required` |
|---|---|---|
| `home` | `schedule.view_shift` (existing) | no |
| `employee_defaults` | `schedule.view_employee` (existing) | no |
| `employee_details` | `schedule.view_employee` | yes (existing) |
| `add_employee` | `schedule.add_employee` (existing) | **add** |
| `schedule_change` | `schedule.change_shift` (existing) | **add** |
| `schedule_add` | `schedule.change_shift` (existing) | **add** |
| `pattern_edit` | `schedule.change_shift` (existing) | **add** |
| `pattern_form_preview` | `schedule.change_shift` (existing) | **add** |
| `delete_pattern` | `schedule.delete_shift` (existing) | **add** |
| `send_welcome` | `schedule.add_employee` (existing) | **add** |
| `set_override` | in-body (existing) | **add** |
| `set_day_override` | `schedule.change_shift` (existing) | **add** |
| `settings_home` | `schedule.view_employee` | yes (existing) |
| `settings_deactivate_employee` | `schedule.change_employee` | yes (existing) |
| `settings_cancel_deactivation` | `schedule.change_employee` | yes (existing) |
| `settings_reactivate_employee` | `schedule.change_employee` | yes (existing) |
| `settings_add_title` | `schedule.add_title` | yes (existing) |
| `settings_delete_title` | `schedule.delete_title` | yes (existing) |
| `settings_add_role` | `schedule.add_role` | yes (existing) |
| `settings_delete_role` | `schedule.delete_role` | yes (existing) |
| `settings_move_role` | `schedule.change_role` | yes (existing) |
| `print_schedule` | `schedule.view_shift` | yes (existing) |

**Notes:**

- `schedule.change_employee` / `change_role` / `change_title` etc. are
  Django's auto-generated per-model permissions. They exist without
  needing any `Meta.permissions` declaration.
- `set_override` has no top-level decorator today (permissions are
  checked in-body based on `action`). Add the in-body
  `management_required` check next to the existing permission checks.
- If any of these views should NOT get management (e.g. you decide
  `print_schedule` doesn't warrant it), flip it before writing code.
  Current plan keeps print on management to match today's behavior.
- `settings_home` currently has no `permission_required` decorator —
  only `management_required`. Add
  `permission_required("schedule.view_employee")` so the machine
  check runs. Same for its write children: add matching
  `permission_required` alongside the existing `management_required`.

### Templates — UI layer

Every `{% if perms.schedule.X %}` becomes `{% if is_management %}`.
Files with perms checks that need conversion:

- `schedule/templates/schedule/home.html` — 3 checks
- `schedule/templates/schedule/employee_defaults.html` — 2 checks
  (in the footer block)
- `schedule/templates/schedule/pattern_form.html` — 1 check
  (delete-pattern button)
- `schedule/templates/schedule/partials/_page_header.html` — 1 check
- `schedule/templates/schedule/partials/_schedule_table.html` — 1 check
  (day-override clickability)
- `schedule/templates/schedule/partials/_schedule_row.html` — 2 checks
  (employee name link, cell button interactivity)
- `schedule/templates/schedule/partials/_identity_form.html` — 1 check
  (Set Last Day button)
- `schedule/templates/schedule/modals/_override.html` — 2 checks
  (Mark off / Reset buttons, Save button)

**`can_change` / `can_delete` context vars:** computed in
`_employee_page_context` from `request.user.has_perm(...)`. Change
both to compute from `is_management(request)`. The
`_saved_patterns.html` template needs no change — it just reads the
context vars.

**Non-Management users with the underlying permission:**
`home` and `employee_defaults` stay permission-only, so a
permission-holder who is not in Management sees:

- Home schedule (yes — `view_shift` is enough)
- Employee reading page (yes — `view_employee` is enough)
- All write buttons hidden, all write modals not rendered
- Any direct URL hit to a write view returns 403 (management gate)

This is the intended shape: read the schedule, do nothing with it.

## CSP plan (Phase 1)

Install `django-csp` (or a small custom middleware; `django-csp` is
the smaller change). Ship:

```
Content-Security-Policy:
  default-src 'self';
  script-src 'self' 'unsafe-inline';
  style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;
  font-src 'self' https://fonts.gstatic.com;
  img-src 'self' data:;
  connect-src 'self';
  frame-ancestors 'none';
  base-uri 'self';
  form-action 'self';
```

Justifications:

- **`script-src 'unsafe-inline'`** — Alpine `x-data` / `x-effect` /
  `x-init` attributes and every HTMX-fragment `<script>` block
  (`_page_state.html`, `_pattern_form_body.html`, `_saved_patterns.html`,
  the modal scripts). Phase 2 will convert these to nonces.
- **`style-src 'unsafe-inline'`** — Tailwind's `@starting-style` in
  `base.html`, Alpine `:class` transitions, and any inline `style="..."`
  attributes.
- **`fonts.googleapis.com` / `fonts.gstatic.com`** — the
  `@import url(...)` at the top of `styles.css` (served same-origin but
  loads CSS from googleapis) and the Space Grotesk / Inter font files
  from gstatic.
- **`frame-ancestors 'none'`** — overlaps with `X-Frame-Options: DENY`
  (already set). Defense in depth; both are harmless together.
- **No `report-uri` on day one.** Deploy enforce mode, watch the browser
  console manually for `Content-Security-Policy` blocks during QA. If
  something breaks, temporarily switch to
  `Content-Security-Policy-Report-Only` while iterating.

Nonces (Phase 2) require:

1. Per-request nonce middleware
2. `nonce="{{ request.csp_nonce }}"` on every inline `<script>` across
   ~10 partials
3. Alpine's CSP build (`@alpinejs/csp`) — because Alpine 3's default
   build uses `new Function()` internally, which CSP blocks. Switching
   means rewriting every `x-data="{ ... }"` to the CSP-compatible form.

That is its own session. Phase 1 is the right scope for this branch.

## Order of operations

Each step is its own commit. Small diffs, easy bisect if something
breaks.

1. **Branch + seed docs** — this file, BUGREPORT update, ISSUES cleanup.
2. **Settings flags (SEC-005).** Conditional `SECURE_*` block in
   `settings.py`, gated on `not DEBUG`. Verify
   `DJANGO_DEBUG=false check --deploy` is clean.
3. **CSP Phase 1 (SEC-001).** Middleware, initial policy, deploy, QA.
4. **Write-access backend (SEC-006, backend).** Decorator changes,
   in-body `set_override` check. Tests for the new gates.
5. **Write-access UI (SEC-006, UI).** Template perms → `is_management`,
   `can_change` / `can_delete` context var refactor.
6. **Header hygiene (SEC-002, SEC-003, SEC-004).** CSRF exclusion in
   HTMX preview, CORS audit + removal, proxy Server strip.
7. **Verify SEC-007.** Submit an invalid signup, inspect re-rendered
   password input. Fix if echoed.
8. **Final sweep.** Re-run `check --deploy` on prod config. Re-run ZAP
   against production. Suppress the SQLi FP in the ZAP context. Update
   this doc with final state.

## Testing strategy

- **Settings flags (SEC-005):** `SimpleTestCase` that asserts each flag
  is `True` when `settings.DEBUG` is `False` (use `override_settings`
  + re-import, or a small helper that reloads the settings module).
- **CSP (SEC-001):** no automated test. Manual browser QA: HTMX swaps
  work, Alpine modals open, fonts render, zero CSP errors in console.
- **Write-access backend (SEC-006):** extend `test_views_edges.py` with
  per-view access cases. For each view: unauthenticated → redirect;
  permission-only user (has the perm, not Management) → 403;
  Management user → passes.
- **Write-access UI (SEC-006):** template-content tests that assert
  write buttons absent for non-Management, present for Management.
- **HTMX CSRF exclusion (SEC-002):** unit test that the preview URL
  produced by the cycle/week pickers does not contain
  `csrfmiddlewaretoken`.

## Deployment caveats

- **HSTS is one-way in practice.** Browsers cache the
  `Strict-Transport-Security` header for the configured duration.
  Start at `SECURE_HSTS_SECONDS = 3600`. After 2–4 weeks of stable
  HTTPS, ramp to `31536000`. Do not enable `SECURE_HSTS_PRELOAD` until
  committed to HTTPS forever.
- **`SECURE_SSL_REDIRECT` in dev** breaks local HTTP testing. Gate on
  `not DEBUG` (already planned).
- **`SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`**
  requires the reverse proxy to send `X-Forwarded-Proto: https`.
  Verify the tunnel / proxy does before shipping — otherwise the
  redirect loops.
- **CSP enforce mode ships hot.** If a template conditionally loads
  an external resource you forgot to allowlist, users see a broken
  page. First-hour monitoring matters. Have a one-line rollback ready
  (comment out the middleware).

## ZAP re-scan after

Re-run ZAP against **production** (not dev). Expected state:

- High/medium findings: zero. (SQLi FP suppressed, CSP + HSTS +
  Secure cookie flags + CORS resolved.)
- Low findings: server header stripped at proxy (if configurable);
  otherwise remains.
- Informational findings: unchanged (tech detection, session mgmt,
  etc.).

Save the post-scan report under `docs/security/zap-post-sweep.html`
for the record.

## Decision log

- **2026-10-27** — Write-access model: `permission_required` on every
  view; `management_required` layered on writes / destructive / tenant
  config. UI gated on `is_management`. Rationale: single permission
  layer as the machine-checkable gate; management as the practical
  policy layer. The permission layer stays in place so a future
  non-Management Scheduler role can be granted write access by adding
  the permission, at which point the UI gating would also change.
- **2026-10-27** — CSP Phase 1 with `'unsafe-inline'`. Nonces deferred.
  Rationale: Alpine's inline `x-data` attributes and HTMX-fragment
  script blocks make nonces a session of their own (Alpine CSP build,
  ~10 template conversions). Phase 1 blocks external-script injection
  which is the majority of the XSS surface. Ship now, tighten later.