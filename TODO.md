# TODO

## Recently completed

- ✅ Fixed `_employees_for_week` multi-join bug (employees appearing in
  gaps between non-overlapping employment periods)
- ✅ Earliest pattern slides both directions when `start_date` changes
- ✅ `delete_pattern` authority aligned with `delete_shift`
- ✅ Transaction wrapping on `add_employee`, `_handle_identity_post`, and
  the three settings deactivation/reactivation views
- ✅ Migration 0002 (temporal patterns) squashed and merged
- ✅ Default `effective_from` splits first-time-setup from forward edits
- ✅ Print schedule feature (multi-week, colour/BW, QR code, config bar,
  icon partial, home modal + button)
- ✅ `APP_NAME` env var wired through templates and emails
- ✅ Test email command uses `settings.SITE_URL` and `settings.APP_NAME`
- ✅ HTMX + Alpine vendored and wired
- ✅ Schedule table split into partials
- ✅ Override modal converted to HTMX + Alpine with tooltips
- ✅ Day-override modal converted to HTMX + Alpine
- ✅ Add-employee modal converted to HTMX + Alpine with tooltips
- ✅ Print modal Alpine open/close with shared transition
- ✅ Shared `.modal-animate` transition in base.html
- ✅ Template reorganization (pages / partials / modals)
- ✅ `employee_defaults.html` split into partials and modals
- ✅ Out-of-band message swap so success flashes show after HTMX saves

## Next branch

- **Alpine pass on `employee_defaults.html`** — week tabs, pattern strip
  pagination, and saved-patterns expand/collapse are still vanilla JS
  IIFEs. Convert to Alpine components the same way the home page modals
  were converted. No view changes expected.

## Follow-up branches

### Delete-pattern HTMX
- Convert the two delete-pattern entry points on the employee page to
  HTMX (the loaded form's Delete button and each saved row's Delete).
- View returns the pattern strip + saved list as fragments; HTMX swaps
  in place. Modal closes with the shared animation.
- Edge case: if the deleted pattern was the one loaded in the defaults
  form, the form needs to re-render from the new latest pattern or the
  user needs a redirect. Decide before building.

### Toasts
- PrimeVue-style notification stack: top-right, auto-dismiss after a
  few seconds, manual close, stacked with a cap.
- Variants mapped to the brand palette (success, error, warning, info).
- Trigger from Django messages framework on page load, plus an
  `HX-Trigger` header mechanism for HTMX responses that don't reload.
- Replaces the out-of-band `_messages.html` swap currently used.
- Accessibility: `role="status"` for non-error, `role="alert"` for error.

### Passkeys (WebAuthn)
- Additive to password + OTP, not a replacement.
- Credential model: `(user, credential_id, public_key, sign_count,
  transports, aaguid, nickname, created_at, last_used_at)`.
- Registration flow from Settings. Authentication flow on login.
- Cross-device hybrid is free if `authenticatorAttachment` isn't
  forced to "platform".
- Library: prefer `django-allauth`'s bundled WebAuthn support. Fall
  back to `py_webauthn` if allauth doesn't fit.
- Keep passwords mandatory; no passkey-only recovery flow yet.
- Testing note: WebAuthn can't be exercised in Django's test client —
  unit-test challenge/response logic and cover UI manually.

## Priority feature work

- **Bulk day editing** — select a range of dates, set them all at once.
  Natural HTMX candidate.
- **Configurable display days** — Settings option: Mon–Sat / Mon–Fri /
  Tue–Sun / all 7 / custom. Replaces hardcoded `DAYS` and `DAY_LABELS`
  in `views.py`. Print view inherits automatically since it reads
  `week.day_headers`.
- **Empty-state UX on home** — no employees, no patterns, no shifts for
  the week.
- **Batch override notifications** — one email for a range of override
  changes instead of N.
- **OTP autofill suppression on password change** — small.
- **Admin login template restyle** — match the brand.

## Print feature follow-ups

- **Paper size configurable** — currently hardcoded `size: letter
  landscape` in `@page`. Add once multi-tenancy lands.
- **Print overflow toggle** — currently each week moves to a new page if
  it doesn't fit; add option to allow overflow onto the next page.
- **QR branding refinement** — replace placeholder side text
  ("Principia Systems") and refine icon overlay. Do once the brand is
  settled and the favicon SVG is final.
- **Company name + team in print header** — currently reads
  `{{ app_name }}`. Fetch from Company/Team models after multi-tenancy.

## Mobile / accessibility follow-ups

- **Print view on mobile** — designed around Letter landscape; on a
  phone the config bar, grid, and QR block need a mobile-first pass.
  Decide whether print output itself needs adjusting (probably not)
  versus just the on-screen preview.
- **Employee defaults hours form not horizontally scrollable on mobile** —
  the week-panel tables overflow with no scroll affordance. Wrap in
  `overflow-x-auto` or restructure for mobile — cards per day or
  vertical field-per-row under a breakpoint. Verify on a real phone
  viewport, not just DevTools.
- **Per-field tooltip dirty tracking** — currently one interaction with
  any field reveals all tooltips. Per-field dirty flags if the current
  behavior feels abrupt.

## Tests

- **HTMX view branches** — the `is_htmx` path in `set_override`,
  `set_day_override`, and `add_employee` isn't covered by the current
  suite. Add tests for the success fragment response and the
  validation-failure retarget response.

## Standing architectural notes

### Multi-tenancy (Company + Team)
Keep in mind as features land, not a next-session item. The point is to
avoid painting ourselves into a corner.
- Every new domain model gets a `company` FK when it's created — even
  if it's always the same value for now. Retrofitting is the expensive
  part.
- Any new queryset helper should take a company parameter in its
  signature, even if callers pass the single default company.
- Don't build `Membership`/`Team`/permission rework yet. Just don't
  design anything that blocks it.
- **Single chokepoint already in place:** `work_schedule/context_processors.py:app_name`
  — when multi-tenancy lands, resolve from `request.company` here and
  every template updates at once.
- **Emails need separate treatment** — no request, so `send_email` will
  need to accept an optional `company` and resolve `app_name` from it.

### Licensing / SaaS infrastructure
- Blocked by multi-tenancy. Plans, entitlements, Stripe integration,
  signup flow, admin console. Don't start until Company model exists.
- First step when we pick it up: a design doc, not code.

### Encryption of sensitive data at rest
- Trigger: customer asks, or regulatory scope (PIPEDA/PHIPA/HIPAA)
  becomes relevant.
- Level 1: disk-level encryption (already have, doesn't protect dumps).
- Level 2: encrypted backups (`pg_dump | age -r ...`) — cheap, catches
  backup leaks, no app changes.
- Level 3: column-level encryption for `Employee.email`, `User.email`,
  and future PII. Hard parts: key management, broken search/sort/unique
  constraints, key loss = data loss.
- Parallel, cheaper: PII in application logs — worth auditing before
  level 3.

## Infra / cleanup

- **Prune `axes_accesslog` periodically** — management command + cron,
  or a `django-axes` retention setting.
- **Verify Tailwind binary cache volume** — confirm it persists between
  deploys.
- **Migration runbook** — short `MIGRATIONS.md`: back up before
  migrate, rehearse on a dump, order of operations, how to restore.
- **Backup verification** — periodically test that a prod backup
  actually restores.
- **Add `htmlcov/` to `.gitignore`** and `git rm -r --cached htmlcov/`.
- **Docstrings on test methods** — opportunistic only.