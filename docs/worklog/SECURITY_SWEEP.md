# Security sweep — branch plan

## Status

**Complete.** All in-scope items done or verified-no-op. Awaiting
CodeRabbit re-review, then merge to staging for ZAP re-scan.

- **SEC-001 (CSP Phase 1):** deferred to a follow-up branch (see
  "CSP plan (deferred)" below).
- **SEC-002:** ✅ done — `hx-params="not csrfmiddlewaretoken"` on
  preview-triggering elements.
- **SEC-003:** ✅ done — `WHITENOISE_ALLOW_ALL_ORIGINS = False`.
- **SEC-004:** ✅ verified no-op — Cloudflare Tunnel replaces the
  `Server` header with `server: cloudflare`. Confirmed against prod.
  No proxy config needed; reopens if the deploy topology ever
  bypasses Cloudflare.
- **SEC-005:** ✅ verified already implemented — `SECURE_*` block
  gated on `DJANGO_SECURE`; both envs correct.
  `DJANGO_DEBUG=false DJANGO_SECURE=true manage.py check --deploy`
  clean.
- **SEC-006:** ✅ complete — every view has `permission_required`;
  `management_required` layered on writes / destructive / tenant
  config. UI AND-gated. 443 tests passing.
- **SEC-007:** ✅ verified false positive — Django's `PasswordInput`
  defaults to `render_value=False`; `SignUpForm` doesn't override.
  No code change.
- **CodeRabbit findings #1–#4:** ✅ fixed (see `FIXED.md`).
- **CodeRabbit finding #5:** ⏭ deferred to `ISSUES.md` — needs an
  `approved_at` field, its own branch.

## Why this branch exists

Session 9's QA pass surfaced hardening items that don't belong in a
feature branch. ZAP against dev, `check --deploy` against current
settings, and the write-access item carried from `ISSUES.md` all
converge here.

Scope discipline: **good not perfect.** Fix the real risks, close the
real inconsistencies, defer the deep work (nonces, HSTS preload,
dependency scanning) to their own branches.

## In scope

- ~~Write-access model refactor — backend and UI (SEC-006)~~ ✅
- ~~Server header strip at proxy (SEC-004)~~ ✅ verified already handled
- ~~Manual verification of password-echo on signup error (SEC-007)~~ ✅ verified false positive

(Done on this branch: SEC-002, SEC-003, SEC-006, CodeRabbit #1–#4.
Verified-no-action: SEC-004, SEC-005, SEC-007. Deferred: CodeRabbit
#5, CSP Phase 1.)

## Out of scope (future branches)

- **CSP Phase 1 (SEC-001).** `default-src 'self'` + `'unsafe-inline'`
  for script/style, `frame-ancestors 'none'`, `form-action 'self'`,
  `connect-src 'self'`. Full policy preserved at the bottom of this
  file for when its branch starts.
- **CSP Phase 2:** nonces, drop `'unsafe-inline'`. Requires Alpine's
  CSP build and rewriting every `x-data` / `x-effect` / `x-init` plus
  ~10 inline `<script>` blocks. Own session.
- **Accounts test layout** — `accounts/tests.py` → `accounts/tests/`
  package. Own branch. Also where the deferred SEC-007 automated
  test lands.
- **Reactivation/reactivation privilege confusion** — CodeRabbit
  finding #5. Own branch; needs `approved_at` field plus migration.
  See `ISSUES.md`.
- HSTS preload (`preload` needs 3+ months of stable HTTPS)
- Dependency vulnerability scanning
- Audit logging / SIEM
- Rate limiting beyond `django-axes`
- Origin checking changes (modern Django defaults are fine)

## Findings triage

### `check --deploy` warnings — SEC-005 (verified, no code change)

All four `SECURE_*` warnings (W004, W008, W012, W016) are already
addressed by the existing `SECURE` block in `settings.py`. W018
(`DEBUG=True`) is dev-only. Verified clean on this branch:
`DJANGO_DEBUG=false DJANGO_SECURE=true manage.py check --deploy`.

### ZAP — false positives (mark in ZAP, no code change)

> **Attribution note (SEC-003).** The `Cross-Domain Misconfiguration`
> instances ZAP returned are on third-party CDNs (`fonts.googleapis.com`,
> `fonts.gstatic.com`, `static.cloudflareinsights.com`) — not on the
> app's own `/static/` paths. Our static assets don't emit
> `Access-Control-Allow-Origin: *` (validated: `WHITENOISE_ALLOW_ALL_ORIGINS = False`
> in `settings.py`).

- **SQL Injection on `/accounts/login/`** — evidence shows a 429
  lockout response; ZAP flagged SQLi because two 429 pages differed
  (dynamic CSRF token in the body). Django ORM auth is parameterized.
  Suppress in ZAP context.
- **Timestamp Disclosure (`?v=...`)** — WhiteNoise cache-buster.
- **Suspicious Comments** — ZAP's `USER` pattern matched "user" in a
  JS comment.
- **Cookie No HttpOnly Flag (csrftoken)** — intentional. HTMX reads
  the CSRF cookie and sets `X-CSRFToken`; HttpOnly would break it.
- **Password field echo (SEC-007)** — verified false positive. ZAP
  was reading its own request payload, not the response HTML. See
  `FIXED.md`.
- **Authentication Request / Session Management / Tech Detected /
  Modern Web App / User Agent Fuzzer / Re-examine Cache-control** —
  informational.

### ZAP — real, actionable

| SEC | Alert | Fix |
|---|---|---|
| SEC-002 | Sensitive Info in URL (`csrfmiddlewaretoken`) | ✅ `hx-params="not csrfmiddlewaretoken"` |
| SEC-003 | Cross-Domain Misconfiguration (`ACAO: *`) | ✅ `WHITENOISE_ALLOW_ALL_ORIGINS = False` (third-party CDNs unfixable) |
| SEC-004 | Server Leaks Version (`WSGIServer/...`) | ✅ verified — Cloudflare strips |
| SEC-006 | Write-access model inconsistency | ✅ permission + Management, AND-gated |
| SEC-007 | Password field echo | ✅ verified false positive |

### CodeRabbit — post-fix scan (revision `250e184`)

| # | Category | Fix |
|---|---|---|
| 1 | Signup OTP stale session (`broken_auth`) | ✅ `_pending_signup_eligible` + `select_for_update` revalidation |
| 2 | Admin password_change bypass (`broken_auth`) | ✅ `admin.site.password_change` overridden |
| 3 | Write endpoints leak read data (`authz_bypass`) | ✅ read-perm `@permission_required` on 7 views |
| 4 | Axes admin add-permission gap (`authz_bypass`) | ✅ `has_add_permission → is_superuser` |
| 5 | Cancel/reactivate activates pending accounts (`authz_bypass`) | ⏭ deferred to `ISSUES.md` — needs `approved_at` field |

## View + UI gating

### Views — permission layer

Every view has a `permission_required` decorator. Writes, destructive
actions, and tenant config also have `management_required`, outermost.
`set_override` is the sole exception: it has an in-body `is_management`
check alongside its existing action-dependent perm branch (no decorator
because the perm varies per `action` value).

| View | `permission_required` | `management_required` |
|---|---|---|
| `home` | `schedule.view_shift` | no |
| `employee_defaults` | `schedule.view_employee` | yes |
| `employee_details` | `schedule.view_employee` | yes |
| `add_employee` | `schedule.add_employee` + `schedule.view_shift` | yes |
| `schedule_change` | `schedule.change_shift` + `schedule.view_employee` | yes |
| `schedule_add` | `schedule.change_shift` + `schedule.view_employee` | yes |
| `pattern_edit` | `schedule.change_shift` + `schedule.view_employee` | yes |
| `pattern_form_preview` | `schedule.change_shift` + `schedule.view_employee` | yes |
| `delete_pattern` | `schedule.delete_shift` | yes |
| `send_welcome` | `schedule.add_employee` | yes |
| `set_override` | in-body (per-action) + `schedule.view_shift` | in-body |
| `set_day_override` | `schedule.change_shift` + `schedule.view_shift` | yes |
| `settings_home` | `schedule.view_employee` | yes |
| `settings_deactivate_employee` | `schedule.change_employee` | yes |
| `settings_cancel_deactivation` | `schedule.change_employee` | yes |
| `settings_reactivate_employee` | `schedule.change_employee` | yes |
| `settings_add_title` | `schedule.add_title` | yes |
| `settings_delete_title` | `schedule.delete_title` | yes |
| `settings_add_role` | `schedule.add_role` | yes |
| `settings_delete_role` | `schedule.delete_role` | yes |
| `settings_move_role` | `schedule.change_role` | yes |
| `print_schedule` | `schedule.view_shift` | yes |
| `qr_code` | `schedule.view_shift` | no |

Decorator order: `@login_required` → `@management_required` →
`@permission_required("...", raise_exception=True)` →
`@permission_required("schedule.view_*", raise_exception=True)` (where
applicable, per CodeRabbit #3) → `@require_POST` (innermost).

**Read implies write** for the seven views with a second read-perm
decorator (CodeRabbit #3). A user with `change_shift` but not
`view_employee` can no longer open the pattern edit form. This
eliminates the class of "write endpoint renders protected data"
findings by refusing the operation rather than stripping the response.

### Templates — UI layer

**AND-gate, not replace.** Every `{% if perms.schedule.X %}` is
`{% if is_management and perms.schedule.X %}` unless already nested
inside an `{% if is_management %}` block (in which case the AND is
implicit and the redundant clause is omitted).

Compound OR case (`add_shift or delete_shift`):
`{% if is_management and perms.schedule.add_shift or is_management and perms.schedule.delete_shift %}`
— Django's `and` binds tighter than `or`, so this is
`(management ∧ add_shift) ∨ (management ∧ delete_shift)`.

`can_change` / `can_delete` context vars: computed in
`_employee_page_context` from `is_management(request)` AND the
underlying perm. Templates that read those vars need no gating; the
views layer did it.

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
> Content-Security-Policy:
> default-src 'self';
> script-src 'self' 'unsafe-inline';
> style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;
> font-src 'self' https://fonts.gstatic.com;
> img-src 'self' data:;
> connect-src 'self';
> frame-ancestors 'none';
> base-uri 'self';
> form-action 'self';


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

That is its own session. Phase 1 is the right scope for a future branch.

## Order of operations (record)

Steps 1–6 all completed:

1. ✅ Branch + seed docs
2. ✅ Write-access backend (SEC-006)
3. ✅ Write-access UI (SEC-006)
4. ✅ Header hygiene (SEC-004) — verified handled by Cloudflare
5. ✅ Verify SEC-007 — false positive
6. ✅ Final sweep (this doc) — code complete; ZAP re-scan pending
   staging merge
7. ⏭ ZAP re-scan against staging (post-merge)

## Testing strategy

- **Settings flags (SEC-005):** verified via `check --deploy`.
- **CSP (SEC-001):** no automated test (deferred). Manual browser QA
  when the CSP branch starts.
- **Write-access backend + UI (SEC-006):**
  `Sec006AccessMatrixTests` in `test_views_edges.py` pins the access
  policy per view (anonymous → redirect, perm-only → 403, mgmt+perm →
  not 403). Behaviour tests in per-view files cover the success path.
- **CodeRabbit #1–#4:** covered by existing tests + new
  `accounts/tests/test_axes_admin.py`.

## Deployment caveats

- **HSTS is one-way in practice.** Browsers cache the
  `Strict-Transport-Security` header for the configured duration.
  Start at `SECURE_HSTS_SECONDS = 3600`. After 2–4 weeks of stable
  HTTPS, ramp to `31536000`. Do not enable `SECURE_HSTS_PRELOAD` until
  committed to HTTPS forever. (Current config already at 31536000 —
  confirmed stable.)
- **`SECURE_SSL_REDIRECT` in dev** breaks local HTTP testing. Gated on
  `not DEBUG` (via `DJANGO_SECURE`).
- **`SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`**
  requires the reverse proxy to send `X-Forwarded-Proto: https`.
  Cloudflare Tunnel does this correctly (verified in prod).
- **CSP enforce mode ships hot.** If a template conditionally loads
  an external resource you forgot to allowlist, users see a broken
  page. First-hour monitoring matters. Have a one-line rollback ready
  (comment out the middleware). N/A this branch (deferred).

## ZAP re-scan after

Re-run ZAP against **staging** (not dev, not prod). Staging mirrors
prod behaviour — `DJANGO_DEBUG=false`, same Cloudflare tunnel with
real egress headers, `DJANGO_SECURE=true` — so the surface is
equivalent while traffic is disposable. Prod re-scan is optional and
can follow if staging comes back clean.

Expected state:

- High/medium findings: zero.
- Low: server header gone (Cloudflare), CSP deferred, no other low
  items remaining.
- Informational: unchanged (tech detection, session mgmt, etc.).

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
- **2026-11-01** — SEC-004 verified handled by Cloudflare Tunnel
  (`server: cloudflare` on egress). No proxy config needed. Reopens
  if the deploy topology ever bypasses Cloudflare; fix would be
  `proxy_hide_header Server;` (nginx) or `header { -Server }`
  (Caddy).
- **2026-11-01** — SEC-005 verified already implemented (gated on
  `DJANGO_SECURE`; both envs correct). No code change.
- **2026-11-01** — SEC-006 complete. Every view has
  `permission_required`; `management_required` layered on writes /
  destructive / tenant config. UI is AND-gated (`is_management and
  perms.schedule.X`), not replace — a Management user without the
  perm shouldn't see buttons that would 403 on click. `qr_code`
  stays permission-only. Print stays management-only.
- **2026-11-01** — SEC-007 verified false positive. Django's
  `PasswordInput` defaults to `render_value=False`; `SignUpForm`
  doesn't override. ZAP read its own request payload, not the
  response. No code change; automated test lands with the
  `accounts/` test-layout branch.
- **2026-11-01** — CodeRabbit findings #1–#4 fixed; #5 deferred to
  `ISSUES.md` (needs an `approved_at` field to distinguish pending
  approval from employment-related suspension — its own branch).
- **2026-11-01** — CodeRabbit #3 fix enforces **write implies read**.
  A user with `change_shift` but not `view_employee` can no longer
  open the pattern edit form. Rejected via `@permission_required` for
  the read perm rather than stripping response data — simpler, and
  eliminates a whole class of "minimal response" questions.
- **2026-11-01** — ZAP re-scan deferred to post-staging-merge.
  Staging mirrors prod behaviour, so it's a valid surface for the
  re-scan while traffic is disposable.