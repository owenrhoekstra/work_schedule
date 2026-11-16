# Security sweep — branch record

## Status

**SHIPPING (2026-11-01).** Branch complete and ready to merge to
main. All in-scope items done or verified-no-op; 483 tests passing;
`DJANGO_DEBUG=false DJANGO_SECURE=true manage.py check --deploy`
clean. ZAP against staging is the final gate before main merge;
report lands at `docs/security/zap-post-sweep.html`.

**This document is a permanent record**, not a cleared-at-merge
worklog file. Unlike `worklog/BUGREPORT.md` and `worklog/FIXED.md`
— which are emptied at merge — this file preserves the branch's
audit trail, decision log, and deferred CSP plan for future security
work. If the worklog directory is ever cleared wholesale, move this
file to `docs/security/SECURITY_SWEEP_2026_11.md` to retain it.

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
- **SEC-006:** ✅ complete — every view has `permission_required`;
  `management_required` layered on writes / destructive / tenant
  config. UI AND-gated.
- **SEC-007:** ✅ verified false positive — Django's `PasswordInput`
  defaults to `render_value=False`; `SignUpForm` doesn't override.
  No code change.
- **CodeRabbit #1–#4, #6–#8:** ✅ fixed.
- **CodeRabbit #5:** ⏭ deferred to `ISSUES.md` — needs an
  `approved_at` field, its own branch.

## Why this branch existed

Session 9's QA pass surfaced hardening items that don't belong in a
feature branch. ZAP against dev, `check --deploy` against current
settings, and the write-access item carried from `ISSUES.md` all
converged here.

Scope discipline: **good not perfect.** Fix the real risks, close the
real inconsistencies, defer the deep work (nonces, HSTS preload,
dependency scanning) to their own branches.

## In scope (all completed)

- ~~Write-access model refactor — backend and UI (SEC-006)~~ ✅
- ~~Server header strip at proxy (SEC-004)~~ ✅ verified already handled
- ~~Manual verification of password-echo on signup error (SEC-007)~~ ✅ verified false positive

(Done: SEC-002, SEC-003, SEC-006, CodeRabbit #1–#4, #6–#8.
Verified-no-action: SEC-004, SEC-005, SEC-007. Deferred: CodeRabbit
#5, CSP Phase 1 & 2.)

## Out of scope (future branches)

- **CSP Phase 1 (SEC-001).** See "CSP plan (deferred)" below.
- **CSP Phase 2:** nonces, drop `'unsafe-inline'`. Requires Alpine's
  CSP build and rewriting every `x-data` / `x-effect` / `x-init` plus
  ~10 inline `<script>` blocks. Own session.
- **Reactivation / cancel privilege confusion** — CodeRabbit finding
  #5. Own branch; needs `approved_at` field plus migration. See
  `ISSUES.md`.
- HSTS preload (`preload` needs 3+ months of stable HTTPS)
- Dependency vulnerability scanning
- Audit logging / SIEM
- Rate limiting beyond `django-axes`
- Origin checking changes (modern Django defaults are fine)

## Findings triage

### `check --deploy` warnings — SEC-005 (verified, no code change)

All four `SECURE_*` warnings (W004, W008, W012, W016) addressed by
the existing `SECURE` block in `settings.py`. W018 (`DEBUG=True`) is
dev-only. Verified clean:
`DJANGO_DEBUG=false DJANGO_SECURE=true manage.py check --deploy`.

### ZAP — false positives (marked in ZAP context, no code change)

> **Attribution note (SEC-003).** The `Cross-Domain Misconfiguration`
> instances ZAP returned are on third-party CDNs
> (`fonts.googleapis.com`, `fonts.gstatic.com`,
> `static.cloudflareinsights.com`) — not on the app's own `/static/`
> paths. Our static assets don't emit `Access-Control-Allow-Origin: *`
> (validated: `WHITENOISE_ALLOW_ALL_ORIGINS = False` in
> `settings.py`).

- **SQL Injection on `/accounts/login/`** — evidence shows a 429
  lockout response; ZAP flagged SQLi because two 429 pages differed
  (dynamic CSRF token in the body). Django ORM auth is parameterized.
- **Timestamp Disclosure (`?v=...`)** — WhiteNoise cache-buster.
- **Suspicious Comments** — ZAP's `USER` pattern matched "user" in a
  JS comment.
- **Cookie No HttpOnly Flag (csrftoken)** — intentional. HTMX reads
  the CSRF cookie and sets `X-CSRFToken`; HttpOnly would break it.
- **Password field echo (SEC-007)** — verified false positive. ZAP
  was reading its own request payload, not the response HTML.
- **Authentication Request / Session Management / Tech Detected /
  Modern Web App / User Agent Fuzzer / Re-examine Cache-control** —
  informational.

### ZAP — real, actionable

| SEC | Alert | Fix |
|---|---|---|
| SEC-002 | Sensitive Info in URL (`csrfmiddlewaretoken`) | ✅ `hx-params="not csrfmiddlewaretoken"` |
| SEC-003 | Cross-Domain Misconfiguration (`ACAO: *`) | ✅ `WHITENOISE_ALLOW_ALL_ORIGINS = False` |
| SEC-004 | Server Leaks Version (`WSGIServer/...`) | ✅ verified — Cloudflare strips |
| SEC-006 | Write-access model inconsistency | ✅ permission + Management, AND-gated |
| SEC-007 | Password field echo | ✅ verified false positive |

### CodeRabbit — post-fix scan (revision `250e184` + follow-ups)

| # | Category | Fix |
|---|---|---|
| 1 | Signup OTP stale session (`broken_auth`) | ✅ `_pending_signup_eligible` + `select_for_update` revalidation |
| 2 | Admin password_change bypass (`broken_auth`) | ✅ `admin.site.password_change` overridden + `_OTPGatedUserAdmin` per-user route |
| 3 | Write endpoints leak read data (`authz_bypass`) | ✅ read-perm `@permission_required` on 7 views |
| 4 | Axes admin add-permission gap (`authz_bypass`) | ✅ `has_add_permission → is_superuser` |
| 5 | Cancel/reactivate activates pending accounts (`authz_bypass`) | ⏭ deferred to `ISSUES.md` — needs `approved_at` field |
| 6 | Identity form POST missing write check (`authz_bypass`) | ✅ in-body `change_employee` check on POST branch |
| 7 | Lifecycle button / endpoint perm drift (`authz_bypass`) | ✅ perm alignment per endpoint; settings.html buttons gated |
| 8 | UserAdmin OTP stamp preserved (`broken_auth`) | ✅ clear on successful POST, preserve on GET / validation error |

## View + UI gating

Every view has a `permission_required` decorator. Writes, destructive
actions, and tenant config also have `management_required`, outermost.
`set_override` is the sole exception: it has an in-body `is_management`
check alongside its existing action-dependent perm branch.

| View | `permission_required` | `management_required` |
|---|---|---|
| `home` | `schedule.view_shift` | no |
| `employee_defaults` | `schedule.view_employee` | yes |
| `employee_details` | `schedule.view_employee` (+ in-body `change_employee` on POST) | yes |
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
| `settings_deactivate_employee` | `schedule.delete_employee` | yes |
| `settings_cancel_deactivation` | `schedule.change_employee` | yes |
| `settings_reactivate_employee` | `schedule.change_employee` | yes |
| `settings_add_title` | `schedule.add_title` | yes |
| `settings_delete_title` | `schedule.delete_title` | yes |
| `settings_add_role` | `schedule.add_role` | yes |
| `settings_delete_role` | `schedule.delete_role` | yes |
| `settings_move_role` | `schedule.change_role` | yes |
| `print_schedule` | `schedule.view_shift` | yes |
| `qr_code` | `schedule.view_shift` | no |

**UI gates:**
- Every `{% if perms.schedule.X %}` is `{% if is_management and perms.schedule.X %}`
  unless already nested inside an `{% if is_management %}` block.
- Button gates match endpoint perms exactly (see CR#7 table row).
- `can_change` / `can_delete` context vars computed as
  `is_management AND has_perm`.

**Read implies write:** for the seven views with a second read-perm
decorator (CR#3), a user with `change_shift` but not `view_employee`
cannot open the pattern edit form. Refusal at the door beats
data-stripping.

## CSP plan (deferred — follow-up branch)

> **Why deferred.** Phase 1 with `'unsafe-inline'` doesn't block the
> inline-script XSS surface this app actually has (Alpine `x-data`,
> `x-effect`, inline `onclick=`, seven inline `<script>` blocks in
> modals/partials). It only blocks external-injection, which Django's
> autoescape already makes hard. Phase 2 (nonces + Alpine CSP build)
> is the meaningful version and is its own session. Keep the policy
> below as the starting draft for that branch.
