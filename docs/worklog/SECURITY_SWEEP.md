# Security sweep — branch plan

## Status

In progress.

- **SEC-004: verified already handled.** Cloudflare Tunnel replaces
  the upstream `Server: WSGIServer/...` header with `Server: cloudflare`
  on egress. Confirmed against prod. No proxy config needed. Reopens
  if the deploy topology ever bypasses Cloudflare.
- **SEC-005: verified already implemented.** ... (unchanged) ...
- **SEC-006: backend + UI complete; tests passing.** Full
  `permission_required` coverage on every view; `management_required`
  layered on writes / destructive / tenant config. UI AND-gated
  (`is_management and perms.schedule.X`). `is_management(request)`
  helper centralizes the group check. Access-matrix tests in
  `test_views_edges.Sec006AccessMatrixTests` pin the policy per view.
- **SEC-007: verified false positive.** Django's `PasswordInput`
  defaults to `render_value=False`; `SignUpForm` doesn't override.
  Confirmed by code analysis. ZAP was reading its own request payload.
  No code change. Automated test deferred to the `accounts/`
  test-layout branch.
- **CSP Phase 1: deferred to a follow-up branch.** ... (unchanged) ...

## Why this branch exists

Session 9's QA pass surfaced hardening items that don't belong in a
feature branch. ZAP against dev, `check --deploy` against current
settings, and the write-access item carried from `ISSUES.md` all
converge here.

Scope discipline: **good not perfect.** Fix the real risks, close the
real inconsistencies, defer the deep work (nonces, HSTS preload,
dependency scanning) to their own branches.

## In scope

- Write-access model refactor — backend and UI (SEC-006) ✅
- ~~Server header strip at proxy (SEC-004)~~ ✅ verified already handled
- ~~Manual verification of password-echo on signup error (SEC-007)~~ ✅ verified false positive

(Done on this branch: SEC-002 CSRF-in-URL, SEC-003 CORS on static.
Verified-no-action: SEC-004, SEC-005, SEC-007.)

## Out of scope (future branches)

- **CSP Phase 1 (SEC-001).** `default-src 'self'` + `'unsafe-inline'`
  for script/style, `frame-ancestors 'none'`, `form-action 'self'`,
  `connect-src 'self'`. Full policy preserved at the bottom of this
  file for when its branch starts.
- **CSP Phase 2:** nonces, drop `'unsafe-inline'`. Requires Alpine's
  CSP build and rewriting every `x-data` / `x-effect` / `x-init` plus
  ~10 inline `<script>` blocks. Own session.
- **Accounts test layout** — `accounts/tests.py` → `accounts/tests/`
  package. Own branch.
- HSTS preload (`preload` needs 3+ months of stable HTTPS)
- Dependency vulnerability scanning
- Audit logging / SIEM
- Rate limiting beyond `django-axes`
- Origin checking changes (modern Django defaults are fine)

## Findings triage

### `check --deploy` warnings — SEC-005 (verified, no code change)

All four `SECURE_*` warnings (W004, W008, W012, W016) are already
addressed by the existing `SECURE` block in `settings.py`. W018
(`DEBUG=True`) is dev-only. Final sweep will re-run
`DJANGO_DEBUG=false DJANGO_SECURE=true manage.py check --deploy` and
expect clean output.

### ZAP — false positives (mark in ZAP, no code change)

> **Attribution note (SEC-003).** The `Cross-Domain Misconfiguration`
> instances ZAP returned are on third-party CDNs (`fonts.googleapis.com`,
> `fonts.gstatic.com`, `static.cloudflareinsights.com`) — not on the
> app's own `/static/` paths. Our static assets don't emit
> `Access-Control-Allow-Origin: *` (validated: `WHITENOISE_ALLOW_ALL_ORIGINS = False`
> in `settings.py`). The "CORS on static" framing in the original
> sweep doc was a mistaken reading of the ZAP report.

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
| SEC-002 | Sensitive Info in URL (`csrfmiddlewaretoken`) | ✅ done — `hx-params="not csrfmiddlewaretoken"` |
| SEC-003 | Cross-Domain Misconfiguration (`ACAO: *`) | ✅ done — `WHITENOISE_ALLOW_ALL_ORIGINS = False` (third-party CDNs unfixable) |
| SEC-004 | Server Leaks Version (`WSGIServer/...`) | ✅ verified — Cloudflare strips |
| SEC-006 | Write-access model inconsistency | ✅ done — permission + Management, AND-gated |
| SEC-007 | Password field echo (unverified) | ✅ verified false positive |

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
| `qr_code` | `schedule.view_shift` (**add**) | no |

- **`qr_code`** isn't in the original table. Per policy ("every view
  has a `permission_required`"), add `@permission_required("schedule.view_shift")`.
  `@login_required`-only today. QR is a login URL — no data leak either
  way — but policy consistency wins.

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

**AND-gate, not replace.** Every `{% if perms.schedule.X %}` becomes
`{% if is_management and perms.schedule.X %}`. Rationale: replace
would show buttons to Management users who lack the perm; those 403
on click. AND keeps UI and backend symmetric.

For the two compound checks (`add_shift or delete_shift`) the AND form
is `{% if is_management and perms.schedule.add_shift or is_management and perms.schedule.delete_shift %}` —
Django's `and` binds tighter than `or` so this is the intended
`(management ∧ add_shift) ∨ (management ∧ delete_shift)`.

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

## CSP plan (deferred — follow-up branch)

> **Why deferred.** Phase 1 with `'unsafe-inline'` doesn't block the
> inline-script XSS surface this app actually has (Alpine `x-data`,
> `x-effect`, inline `onclick=`, seven inline `<script>` blocks in
> modals/partials). It only blocks external-injection, which
> Django's autoescape already makes hard. Phase 2 (nonces + Alpine
> CSP build) is the meaningful version and is its own session.
> Keep the policy below as the starting draft for that branch.

[rest of CSP plan unchanged]

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
2. **Write-access backend (SEC-006, backend).** Add `is_management(request)`
   helper; refactor `management_required` to use it; decorator and
   in-body changes per the views table; `_employee_page_context`
   `can_change` / `can_delete` AND-gated; `_home_context` `employee_form`
   gate AND-gated. Tests for the new gates.
3. **Write-access UI (SEC-006, UI).** Template perms → AND-gate.
4. **Header hygiene (SEC-004).** Proxy Server-header strip; doc the
   config.
5. **Verify SEC-007.** Submit an invalid signup, inspect re-rendered
   password input. Fix if echoed.
6. **Final sweep.** Re-run `check --deploy` on prod config. Re-run ZAP
   against production. Suppress SQLi FP in ZAP context. Update this
   doc with final state. Move CSP detail to a dedicated branch plan.

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
- **2026-11-01** — SEC-005 verified already implemented (gated on
  `DJANGO_SECURE`; both envs correct). No code change. CSP Phase 1
  deferred to follow-up branch (marginal value vs Alpine CSP-build
  cost). Write-access: confirmed AND-gate on UI (not replace). Print
  stays management-only. `qr_code` gets `permission_required` per
  policy. SEC-007 test deferred to accounts test-layout branch.
- **2026-11-01** — SEC-004 verified: Cloudflare Tunnel replaces the
  `Server` header on egress with `Server: cloudflare`. No proxy config
  needed. Reopens if the deploy topology bypasses Cloudflare; the fix
  would then be `proxy_hide_header Server;` (nginx) or
  `header { -Server }` (Caddy). Documented for the record, no action now.
- **2026-11-01** — SEC-007 verified false positive. Django's
  `PasswordInput` defaults to `render_value=False`; `SignUpForm`
  doesn't override, and the template uses standard rendering. ZAP was
  reading its own request payload, not the response. No code change;
  automated test lands with the `accounts/` test-layout branch.