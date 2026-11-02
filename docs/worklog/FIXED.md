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
  check --deploy` — clean.
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
- **Decision:** No proxy config needed. Reopens if the deploy topology
  ever bypasses Cloudflare (direct nginx, VPS direct serve); the fix
  would then be `proxy_hide_header Server;` (nginx) or
  `header { -Server }` (Caddy). Noted for the record; no action now.

### SEC-006 — Write-access model inconsistency

- **Severity:** Medium (authorization logic; not a live exploit given
  the current permissions model, but blocks a clean future state)
- **Symptom:** Some views were `management_required`-only; others
  `permission_required`-only. The two layers weren't consistently
  applied, so policy could drift silently.
- **Fix:** Every view now has `permission_required`. Writes,
  destructive actions, and tenant config also have
  `management_required`, outermost. UI gates on
  `is_management and perms.schedule.X` (AND, not replace) so a
  Management user without the underlying perm doesn't see buttons
  that would 403 on click.
- **Key changes:**
  - `schedule/views.py` — new `is_management(request)` helper;
    `management_required` refactored to use it. Decorator added to
    20 views per the sweep table. `_employee_page_context` computes
    `can_change` / `can_delete` as `is_management AND has_perm`.
    `home`'s `employee_form` gate AND-gated. `set_override` gets an
    in-body `is_management` check (no decorator — perm also branches
    per action).
  - Templates (8 files) — mechanical `perms.schedule.X` →
    `is_management and perms.schedule.X`, including compound OR
    cases in `home.html` and `_schedule_row.html`. `employee_defaults.html`
    left alone where perm checks were already nested inside
    `{% if is_management %}` blocks — implicit AND.
  - `schedule/tests/factories.py` — new `make_management_user()`
    consolidating the "perms + Management group" pattern duplicated
    across 6 test files. `make_manager_user()` now grants *all*
    schedule perms via queryset instead of a hardcoded 8-item list
    (pre-SEC-006 that list omitted role/title perms, which now cause
    403s on `settings_*`).
  - `schedule/tests/test_views_edges.py` — new
    `Sec006AccessMatrixTests`: for each of 20 views, three cases
    (anonymous → redirect, perm-only → 403, mgmt+perm → not 403).
    This is the enforcement of the AND-gate policy; individual
    behaviour tests in the per-view files cover the success path.
- **Tests:** 443 passing at time of this entry. `DJANGO_DEBUG=false
  DJANGO_SECURE=true manage.py check --deploy` clean.

### SEC-007 — Verify password field not re-echoed on signup error

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
    rendering); no manual `value=` attribute.
- **Root cause of the ZAP finding:** ZAP reading its own request
  payload, not the response. Matches the "may be a false positive"
  hypothesis in the original sweep triage.
- **Target: verified no-op.** Automated test for this still deferred
  — see `ISSUES.md` ("Waiting on a specific branch") — but the
  `accounts/tests/` package landed on this branch, so it can be
  picked up whenever.

### CodeRabbit #1 — Signup OTP accepts stale sessions

- **Severity:** Low (requires an abandoned mailbox plus access to a
  pending signup session).
- **Symptom:** `verify_signup_otp` reloaded the employee by cached
  ID and checked only `user_id is not None`. If management changed
  the email or deactivated the employee between signup start and
  OTP verification, the old mailbox holder could still complete, and
  the intended owner couldn't.
- **Fix:** `accounts/views.py` — new `_pending_signup_eligible()`
  helper checks email/active/user-link; called before issuing a
  replacement code on resend. Final account creation reloads under
  `select_for_update()` inside `transaction.atomic()` and revalidates
  all three conditions before attaching. Stale sessions get a clear
  message and redirect to `signup`.
- **Tests:** `StalePendingSignupTests` in
  `accounts/tests/test_signup.py` — 6 cases covering email change,
  deactivation, and pre-linked user on both verify and resend paths.
  Verify path mocks `verify_signup_otp` to True so the post-OTP
  revalidation branch is exercised. Resend path asserts
  `send_email` is not called for stale sessions.

### CodeRabbit #2 — Admin password change bypasses OTP gate

- **Severity:** Low (assumes an active `is_staff` account; the admin
  is not externally discoverable beyond the URL, but the bypass is
  real for anyone who finds it).
- **Symptom:** `work_schedule/urls.py` mounts `admin.site`. Django's
  `AdminSite.password_change` uses the standard `PasswordChangeForm`,
  which only checks the current password. `OTPGatedPasswordChangeView`
  only applies to `/accounts/password_change/`, so an `is_staff` user
  could replace their password via the admin URL without ever passing
  the OTP gate.
- **Fix:** `work_schedule/urls.py` — `admin.site.password_change`
  overridden with `_admin_password_change_redirect`, which redirects
  to `password_change` (the OTP-gated view). Prefix-agnostic; works
  wherever `admin.site.urls` is mounted.
- **Tests:** `AdminPasswordChangeRedirectTests` in
  `accounts/tests/test_password_change.py` — 3 cases: GET and POST
  both redirect to `password_change`; the redirect target actually
  hits the OTP gate (`verify_otp`).

### CodeRabbit #3 — Write endpoints render protected data without read perm

- **Severity:** Low (requires a Management user with write but not
  read perms — a misconfiguration, not an attack surface).
- **Symptom:** Several write endpoints rendered roster or saved-pattern
  fragments without checking `schedule.view_shift` /
  `schedule.view_employee`. A caller with `add_employee` but not
  `view_shift` could see roster data via the add-employee modal path.
- **Fix:** `schedule/views.py` — `@permission_required` for the read
  perm added to: `add_employee`, `schedule_change`, `schedule_add`,
  `pattern_edit`, `pattern_form_preview`, `set_override`,
  `set_day_override`. Policy: **write implies read.** Delegation:
  refuse the operation, don't strip the response — simpler, and
  eliminates the "what does the minimal response look like"
  question.
- **Tests:** covered by `Sec006AccessMatrixTests` (perm-only user
  without the read perm gets 403 on the write view).

### CodeRabbit #4 — Axes admin add-permission gap

- **Severity:** Low (requires an `is_staff` account holding
  `axes.add_accessattempt`).
- **Symptom:** `accounts/admin.py` overrides
  `has_view` / `has_change` / `has_delete` / `has_module` to
  superuser-only, but not `has_add`. Django's default checks only the
  model add permission. A non-superuser staff user with
  `axes.add_accessattempt` could create authentication records via
  admin — including failure counters used in lockout decisions.
- **Fix:** `accounts/admin.py` — `has_add_permission` on both
  `AccessAttemptAdmin` and `AccessLogAdmin` returns
  `request.user.is_superuser`.
- **Tests:** `AxesAdminAddPermissionTests` in
  `accounts/tests/test_axes_admin.py` — 4 cases: non-superuser staff
  with the perm gets `False` on both; superuser gets `True` on both.
  Uses the "is_staff + permission" shape, which is what Django's
  default would have accepted — otherwise the tests would pass
  trivially.

### CodeRabbit #7 — Lifecycle action-button / endpoint perm drift

- **Severity:** Low (requires a Management user with a lifecycle
  perm mismatched to their button visibility — a misconfiguration,
  not an attack surface).
- **Symptom:**
  - `settings_deactivate_employee` required `change_employee` while
    its trigger buttons gated on `delete_employee`. A user with
    `delete_employee` but not `change_employee` saw the button and
    got a 403 on click.
  - `settings.html` rendered Deactivate / Cancel deactivation /
    Reactivate / Send welcome buttons **entirely ungated** — a
    perm-less Management user saw all of them.
  - `_identity_form.html` and `employee_defaults.html` gated the
    Cancel deactivation button on `delete_employee`, but its endpoint
    requires `change_employee`.
- **Fix — perm alignment per endpoint (destruction vs restoration):**
  - `settings_deactivate_employee` → `delete_employee` (was
    `change_employee`). Deactivation is destructive: sets
    `is_active = False`, closes an employment period.
  - `settings_cancel_deactivation` — **unchanged at
    `change_employee`**. Restoration, not destruction; matches
    `settings_reactivate_employee`.
  - `settings_reactivate_employee` — unchanged at `change_employee`.
  - `send_welcome` — unchanged at `add_employee`.
- **Fix — button gates aligned to their endpoint's perm:**
  - `settings.html` — Deactivate → `delete_employee`; Cancel
    deactivation → `change_employee`; Reactivate → `change_employee`;
    Send welcome → `add_employee`. All wrapped in
    `{% if is_management and perms.schedule.X %}`.
  - `_identity_form.html` — combined `delete_employee` gate split:
    Cancel deactivation → `change_employee`; Set Last Day →
    `delete_employee`.
  - `employee_defaults.html` — same split.
- **Tests:** `DeactivationPermissionTests` in
  `test_settings.py` — 9 cases: deactivate on `delete_employee` (302),
  deactivate on `change_employee` (403), cancel on `change_employee`
  (302), cancel on `delete_employee` (403), plus 5 settings-page
  button visibility cases.
- **Related:** general class tracked in `ISSUES.md` — "Action-button
  / endpoint permission drift." Rule: the button's gate equals the
  endpoint's perm, nothing more, nothing less.

### CodeRabbit #6 — Identity form POST missing write-permission check

- **Severity:** Low (requires a Management user with `view_employee`
  but not `change_employee` — a misconfiguration, not an attack
  surface).
- **Symptom:** `employee_details` gated on
  `@permission_required("schedule.view_employee")` for both GET and
  POST. POST dispatches to `_handle_identity_post`, which calls
  `form.save()` on the Employee row — a write. A Management user with
  `view_employee` but not `change_employee` could edit identity
  fields. Inconsistent with `settings_deactivate_employee` and
  friends, all of which require an action perm.
- **Fix:**
  - `schedule/views.py` — in-body
    `if not request.user.has_perm("schedule.change_employee"): raise PermissionDenied`
    at the top of the POST branch, before form-type dispatch. Covers
    the "unknown form" branch too. GET unchanged on `view_employee`.
  - `_identity_form.html` — Save details button gated on
    `is_management and perms.schedule.change_employee`.
- **Tests:** `EmployeeDetailsWritePermissionTests` in
  `test_details.py` — 4 cases (GET 200 for view-only, POST 403
  without change_employee + no DB mutation, unknown-form POST 403,
  Save button absent in template).

### HTMX session expiry — redirect to login instead of swapping the login page

- **Severity:** Low (UX breakage, no data exposure).
- **Symptom:** When a session expired and the user clicked Save on an
  HTMX form, `@login_required` returned 302 → login. HTMX followed
  the redirect (browser fetch), got the login page HTML (200), and
  swapped it into the fragment's `hx-target` — usually
  `#schedule-table` or a modal body. User saw the login form
  embedded in a broken page, with no clear error and lost input.
- **Fix:** `work_schedule/middleware.py` — new
  `HTMXLoginRedirectMiddleware`. Detects HTMX request + 3xx to
  `settings.LOGIN_URL`, rewrites to 204 with `HX-Redirect`. HTMX does
  a full-page navigation; `?next=` is preserved so the user lands
  back on the form after re-auth. Also catches the deactivation
  middleware's 302-to-login (same failure mode).
- **Tests:** `HTMXLoginRedirectMiddlewareTests` in
  `schedule/tests/test_middleware.py` — 6 cases covering HTMX
  anonymous (POST/GET), `?next=` preservation, non-HTMX path
  unchanged, authenticated HTMX path unchanged.
- **Not addressed:** 403 on unauthorized-write for logged-in users
  (HTMX silently does nothing on 4xx). Different concern; tracked in
  `ISSUES.md`.