# Session design decisions

Chronological design rationale from each session. Persistent across
branches.

For "what got fixed and how," see `docs/bugs/FIXED.md`. For "what to
do next," see `docs/UX_BACKLOG.md`.

Sessions are numbered by planned work. Decimals (5.5, 6.5, 7.5) are
sub-sessions that emerged during the work — same numbering as the
session planning docs.

---

## Session 5.5 — Calendar alignment

**Principle:** the pattern form's "panel index" is a **calendar-week
index relative to `effective_from`**, not the target pattern's cycle
offset. Panel `i` represents `effective_from + 7*i`.

This keeps prefill, save, and notification diff consistent even when
`effective_from` isn't congruent with `CYCLE_EPOCH` for the target's
cycle length. Save loops translate `(cal_offset, day)` →
`(target_offset, day)` via
`(base_target_offset + cal_offset) % cycle_weeks`.

Technical detail: see `FIXED-003`.

---

## Session 6 — Pattern edit page

1. **`effective_from` derivation.** The entry path determines it.
   "Change from this week" → no week picker; the current week is
   implied. "Add future pattern" → explicit week picker. Edit page →
   the pattern's existing `effective_from`, week picker disabled.

2. **No end-date UI anywhere.** `effective_to` is derived, never set
   directly:
   - On create: predecessor's `effective_to` truncated to the new
     pattern's `effective_from`. The new pattern inherits the
     predecessor's old `effective_to` (or `None` if predecessor was
     open-ended).
   - On delete: predecessor's `effective_to` extended to the deleted
     pattern's `effective_to` (or `None`). Already implemented in
     `delete_pattern`.
   - Otherwise: `None` = open-ended.
   - **Why `effective_to` exists at all:** pre-migration scaffold for
     the (much later) bulk-overrides feature. Until then, no UI sets
     it directly; the schedule resolver uses it to determine which
     pattern covers a given week. Don't add direct-edit UI for it.

3. **Delete confirmation.** Every destructive action requires a
   secondary confirmation. Prefer the modal pattern
   (`_delete_pattern_confirm.html`). Browser `confirm()` only as a
   last resort.

4. **Retroactive.** Confirmation required only when **editing an
   already-saved pattern whose `effective_from` is in the past**.
   Editing is destructive of written history. Creating a new pattern
   at this week does not need retroactive confirmation; it's the
   normal "change now" flow.

5. **Earliest-pattern guard.** The edit page hides the delete button
   when the pattern being edited is the employee's earliest. Server
   guard already exists in `delete_pattern`; keep it — hidden UI is
   not a permission.

6. **Prefill.** Deferred; scope TBD — see Session 6.6 in
   `UX_BACKLOG.md`.

---

## Session 6.5 — Calendar week picker

1. **Calendar modal, not inline.** Vertical form space is tight
   (banner + cycle picker + tabs + grid + footer). Modal gives the
   same calendar affordance without eating form height.

2. **7-day bands (Mon–Sun).** Current schedule only uses Mon–Sat, but
   multi-tenancy will let tenants choose their work days. The modal
   renders 7 days now; a future `data-days` override doesn't require
   a rewrite.

3. **Scope is self-contained.** Alpine component scoped to the dialog
   only. No cross-scope reactivity — same isolation strategy that
   fixed the retroactive-confirm modal in Session 6.

4. **BUG-006 cause removed.** The old 180-day floor existed only
   because the `<select>` couldn't hold unlimited options. The
   calendar picker has no such limit; `_week_picker_options` and its
   fallback logic are gone.

5. **Navigation:** ◀ / ▶ for month step; clicking the month name
   opens a 12-month grid; clicking the year opens a scrollable year
   list (min-year = employee start year, max = today + 5).

6. **Pre-start-date weeks are disabled.** Grays them out; the server
   would reject them anyway via the existing `effective_from <
   start_date_floor` guard, but the UI shouldn't invite the error.

7. **Keyboard:** basic only. Tab between week bands, Enter to select,
   Escape to close. No arrow-key grid navigation — this is a
   click-first app.

---

## Session 7 — Details page

1. **Read-only reading page.** `employee_defaults` is read-only. All
   identity editing and deactivation live at `/details/`. Reading-page
   POST dispatch removed.

2. **`/details/` gated on `@management_required`.** Matches "only
   management can reach the reading page" intent.

3. **Deactivation is a modal, not a page transition.** Every other
   pattern-write flow (change/add/edit) is a full page. Deactivation
   is a single-field confirmation — modal is the right weight.

4. **Standardize `_deactivate.html`.** Self-contained, no Alpine
   dependency (inline `onclick` + `window.openDeactivateModal`).
   Included from both `settings.html` and `employee_details.html`.

5. **`next` field controls redirect after deactivation.**
   `settings_deactivate_employee` reads `next` from POST:
   `employee_defaults` → reading page; anything else →
   `settings_home`. Whitelist; no arbitrary URL redirects.

6. **`_confirm_discard.html` is the standard cancel-with-unsaved-state
   pattern.** Any Cancel button that would abandon edits routes
   through it via `openConfirmDiscardModal(href)`.

---

## Session 7.5 — Employee-UX polish

1. **Edit CTA lives inside the Employee card on the reading page.**
   Small filled coral button in the card footer, right-aligned, gated
   on `is_management`. Label: "Edit employee". No header link.

2. **Confirmation modal for every details-page commit.**
   - Set Last Day → `_deactivate.html` (existing)
   - Cancel deactivation → `_cancel_deactivation_confirm.html` (new)
   - Save details → `_confirm_save_details.html` (new; always shown —
     user preference for explicit action every save. Revisit if it
     becomes noisy.)

3. **Scheduled-deactivation banner** appears above the identity form
   fields when `last_day` is set, naming the date and the fact that
   they're off from the following day.

4. **Cancel deactivation stays on `/details/`** via
   `settings_cancel_deactivation` honouring a `next` POST field
   (mirrors `settings_deactivate_employee`).

---

## Session 8 — Signal removal

1. **No auto-created pattern.** A new Employee has no schedule until
   a manager sets one up. Removing the signal matches the redesign
   principle: reading is summary, writing is deliberate.

2. **Three reading-page states:**
   - Current pattern exists → existing display + Change / Add buttons.
   - No current pattern, past patterns exist → "Not scheduled this
     week" + Change / Add buttons.
   - No patterns at all → "Not scheduled at all" + "Set up schedule"
     CTA (single button, no Change / Add pair).
   - The distinction is exposed via `has_any_patterns` in
     `_employee_page_context`.

3. **Factory defaults to `with_pattern=False`.** Tests opt in
   explicitly via `with_pattern=True` or by passing `cycle_weeks=N`
   (passing cycle_weeks at all implies with_pattern=True, including
   cycle_weeks=1). "Accuracy over minimal churn" — matching the app's
   actual behavior beats preserving test defaults that no longer
   reflect reality.

4. **EmploymentPeriod signal stays.** Only pattern auto-creation
   removed. An employed window is a property of the hire event; the
   pattern is a scheduling decision.

---

## Session 9 — QA + ship

### Pre-QA pass

1. **BUG-003 — server-side grid value preservation.** Grid validation
   collects all errors before re-rendering and stashes every
   successfully-parsed cell into `submitted_shifts` (a dict of
   `SimpleNamespace(start_time, end_time)`). The error re-render uses
   those values instead of covering-pattern prefill. Parse-failed or
   half-parsed cells are dropped — no clean way to render them as a
   Shift-shaped object for the `|time` template filter. Invalid pairs
   (end <= start) ARE stashed so the user sees both values plus the
   error message. Behavior uniform across
   `_handle_pattern_form_post` (change/add) and
   `_handle_pattern_edit_post` (edit).

2. **BUG-007 — client-side grid value preservation.** A `valueCache`
   object inside `_pattern_form_body.html`'s script IIFE snapshots
   visible time input values on `htmx:beforeRequest` when the cycle
   picker fires, and restores them from `htmx:afterSwap` into the
   fresh `#pattern-form-body`. Cache persists across multiple cycle
   changes so shrink-then-grow retains hidden weeks' values. Cleared
   on submit (capture-phase listener; server response becomes source
   of truth) and on week change (different context).

3. **BUG-003/007 scope consciously limited** to time inputs. Notify
   checkbox and retroactive-confirmed hidden input reset on
   cycle-change re-render; leaving for a follow-up if the friction
   surfaces.

4. **Dual-duty retroactive modal.** Retroactive save shows a single
   modal ("Save retroactive changes?") that acts as both the warning
   and the save confirmation. Confirm sets `retroactive_confirmed=1`
   AND `saveConfirmed` and submits directly — no second modal.
   Non-retroactive saves show the generic save confirmation modal
   instead. One modal per save attempt, chosen based on retroactivity.

5. **Confirmations on the pattern form.** Save always routes through
   a confirmation modal (`_confirm_save_pattern.html` or the
   retroactive modal). Cancel routes through `_confirm_discard.html`
   (previously a plain `<a href>` — no discard warning). Both via the
   `_pattern_form_body.html` submit interceptor and inline onclick.

### CodeRabbit passes

6. **Truncated-pattern edit support** (pass 1). A split can leave a
   pattern with `cycle_weeks > span_weeks`. The edit guard now rejects
   only growing past the span (`cycle_weeks > span_weeks AND
   cycle_weeks > pattern.cycle_weeks`); unchanged or reduced cycles
   are allowed. Companion prefill fix: `_grid_weeks_for_form` accepts
   an optional `pattern` argument; edit mode uses direct-pattern
   prefill so unchanged saves don't write next-pattern data into
   hidden offsets. The truncated-edit exception lives only in
   `_handle_pattern_edit_post`; change/add has no such exception
   (see item 12).

7. **Prefill dedupe on cycle extension** (pass 1, change/add only).
   When target cycle exceeds source cycle, later panels that would
   wrap to already-prefilled source offsets are left blank. The user
   is extending the cycle; extra weeks are new territory. Not
   applicable in edit mode (direct prefill can't duplicate).

8. **Reading-page range display shows Mon–Sun** (pass 2). Collapsed
   history rows and the "Currently scheduled" card render
   `last_week + 6 days` (Sunday) instead of `last_week` (Monday), so
   a 1-week pattern reads "Oct 19 through Oct 25" instead of
   "Oct 19 through Oct 19". Banner copy still uses the Monday for
   "until Week of X" phrasing, where a week-starting reference is
   correct.

9. **Retroactive-guard error re-renders preserve grid values**
   (pass 2/3). Grid parse runs before the retroactive guard in both
   handlers so the retroactive error re-render can pass
   `submitted_shifts` and keep the user's typed values. Pre-grid
   errors (effective_from parse, start_date_floor, span guard) can't
   preserve — the user is changing weeks/cycles anyway, and the
   client-side cache is cleared on that change.

10. **Hidden-week POST cells skipped in parse and save loops**
    (pass 3). After the cycle-shrink HTMX swap, `week_2_*` /
    `week_3_*` inputs remain in the POST body even when
    `cycle_weeks=2`. Both `validated_edits` and `submitted_shifts`
    construction skip `cal_offset >= cycle_weeks`, and the save loop's
    modulo translation guards the same condition. Without this, the
    modulo mapping put those hidden cells back onto visible offsets 0
    and 1 (empty = deleted, non-empty = overwrite).

11. **Week picker trigger's `data-selected` kept in sync** (pass 4).
    `pickWeek` writes the picked ISO back into the trigger button's
    `data-selected` attribute as well as its text label. Without this,
    `openFromTrigger` would re-read the stale page-load value on
    reopen and highlight the wrong week.

12. **Target-span check on change/add** (pass 5).
    `_handle_pattern_form_post` computes the target pattern's eventual
    `effective_to` (covering's `effective_to` for edit-in-place and
    split; next pattern's `effective_from` for new) and rejects
    `cycle_weeks > span_weeks` before opening the transaction. No
    `covering.cycle_weeks` exception — the truncated-edit path stays
    on `/patterns/<uuid>/`. Without this, a change at a
    2-week-remaining span with `cycle_weeks=4` would create a pattern
    whose offsets 2 and 3 never display.

### Infrastructure / hardening

13. **Aria labels on every modal.** `aria-labelledby` on five modals
    (`_cancel_deactivation_confirm`, `_confirm_discard`,
    `_confirm_save_details`, `_deactivate`, `_retroactive_confirm`)
    plus `_confirm_save_pattern`; `_week_picker` gets
    `aria-label="Choose a week"` with per-week-band `aria-label`s.

14. **`settings_deactivate_employee` redirect fallback.** When
    `is_immediate` (last_day in the past), the redirect target is
    always `settings_home` regardless of the `next` POST field. The
    reading page's filter excludes `last_day < today`, so honouring
    `next=employee_defaults` on an immediate deactivation would 404.
    Non-immediate deactivations still honour `next`.

15. **`restore_local_db.py` hardening.** Pre-flight checks (psql,
    gunzip, cat, gzip -t integrity) run before the destructive reset.
    PGPASSFILE (temp file, 0600, cleaned in `finally`) replaces
    PGPASSWORD env-var injection. psql runs with `-X`,
    `-v ON_ERROR_STOP=1`, `--single-transaction`. stderr streams
    live. Both subprocess return codes checked, psql-first (producer
    SIGPIPE is a consequence, not a cause). Docstring explicitly
    separates what pre-flight catches (missing tools, corrupt .gz)
    from what it doesn't (invalid SQL — reset already dropped the DB;
    `--single-transaction` rolls back to empty).

---

## Session 10 — Security sweep

Branch-level hardening pass. Session 9's QA and the ZAP scan both fed
into it; the write-access item carried from `ISSUES.md` was its first
job. See `docs/security/SECURITY_SWEEP.md` for the item-by-item record.

1. **Write-access model — permission-first, Management as a layer.**
   Every view has `permission_required`. Writes, destructive actions,
   and tenant config also have `management_required`, applied
   **outermost** so a non-Management user gets a uniform 403 before
   the perm check runs. `is_management(request)` is the single source
   of truth for the group check; `management_required` uses it, and
   view bodies / context builders use it for UI AND-gating.

2. **AND-gate on UI, not replace.** Every `{% if perms.schedule.X %}`
   becomes `{% if is_management and perms.schedule.X %}` unless
   already nested inside an `{% if is_management %}` block.
   Rationale: **replace** would show buttons to a Management user who
   lacks the underlying permission — those clicks would 403. **AND**
   has no such failure mode; the UI and backend stay symmetric by
   construction.

3. **Write implies read.** Seven write views got a second
   `@permission_required` for the read perm they render
   (`add_employee`, `schedule_change`, `schedule_add`, `pattern_edit`,
   `pattern_form_preview`, `set_override`, `set_day_override`).
   Refusing the operation was chosen over stripping the response:
   simpler, and eliminates a class of "what does the minimal response
   look like" questions. A user with write but not read perms is a
   misconfiguration, and refusing is the right failure mode for it.

4. **`set_override` exception.** It has no `management_required`
   decorator because its perm also branches per `action` (delete for
   `off` / `reset`, add for `save`). The `is_management` check runs
   in-body at the top of the function, before the action branch,
   matching the same failure shape as the decorator would.

5. **`qr_code` is permission-only, not management.** The QR is a
   login URL and carries no data. Policy consistency wins (every view
   has a perm), but layering Management on top would add friction
   with no security benefit. Login already requires an account; the
   QR just points at the form.

6. **`print_schedule` stays management-only.** Confirms Session 7's
   read/write distinction — print is a bulk data export, not a
   personal view. Management + `view_shift` both required.

7. **Factory consolidation.** New `make_management_user()` collapses
   the "perms + Management group" pattern duplicated across six test
   files. `make_manager_user()` now grants every `schedule.*`
   permission via queryset rather than a hardcoded 8-item list — the
   missing role/title perms became 403s the moment `settings_*` views
   got their `@permission_required` decorators.

8. **Access matrix test.** `Sec006AccessMatrixTests` in
   `test_views_edges.py` pins the policy per view: anonymous →
   login redirect, perm-only → 403 (Management gate fires),
   mgmt+perm → not 403. Three assertions per view × 20 views.
   Behaviour tests in per-view files cover the success path;
   the matrix covers the authorization policy itself, so decorator
   wiring can't drift silently.

9. **`check --deploy` verification.** `DJANGO_DEBUG=false
   DJANGO_SECURE=true manage.py check --deploy` clean. Confirms the
   SEC-005 `SECURE_*` block works end-to-end for a prod-config run.

10. **CodeRabbit follow-ups.** Four additional findings landed
    cleanly:

    - **Signup OTP stale session.** Final OTP verification now
      reloads the employee under `select_for_update()` inside
      `transaction.atomic()` and revalidates email / active /
      user-link before attaching. Resends check the same conditions
      before issuing a replacement code. Rejects the "management
      changed the email but old holder completed" scenario.
    - **Admin password_change bypass.** `AdminSite.password_change`
      is overridden in `work_schedule/urls.py` to redirect to the
      OTP-gated `/accounts/password_change/` flow. Prefix-agnostic
      (works at `/admin/`, `/back-panel.../`, wherever mounted).
    - **Write endpoints leak read data.** Covered by (3) above.
    - **Axes admin `has_add_permission`.** Both
      `AccessAttemptAdmin` and `AccessLogAdmin` override it to
      superuser-only, matching the other permission methods. Django's
      default would have accepted any `is_staff` user with
      `axes.add_accessattempt`.

    Fifth finding (reactivate/cancel activates pending-approval
    accounts) is deferred — needs a distinct `approved_at` field to
    separate "account approved" from "employment active." Deferred
    to `ISSUES.md`; its own branch.

11. **Verified-no-op items.**
    - **SEC-004 (server header leak).** Cloudflare Tunnel replaces
      the upstream `Server` header with `server: cloudflare`.
      Confirmed via `curl -sI` against prod.
    - **SEC-005 (`SECURE_*` settings).** Already implemented; gated
      on `DJANGO_SECURE`; both envs correct.
    - **SEC-007 (password echo).** ZAP was reading its own request
      payload. `PasswordInput` defaults to `render_value=False` and
      `SignUpForm` doesn't override it.

12. **ZAP re-scan deferred to staging.** Staging mirrors prod
    behaviour (`DJANGO_DEBUG=false`, same Cloudflare tunnel, real
    egress headers, `DJANGO_SECURE=true`), so it's a valid surface
    for the re-scan while traffic is disposable. Prod re-scan
    optional after staging goes clean.

13. **HTMX session-expiry handling.** `HTMXLoginRedirectMiddleware`
    catches HTMX requests that redirect to `settings.LOGIN_URL` and
    rewrites to `204 + HX-Redirect`. Without it, HTMX follows the 302,
    receives the login page HTML (200), and swaps it into the fragment
    target — the user sees a login form embedded in a schedule slot.
    Also catches the deactivation middleware's kick-out redirect
    (same failure mode). Placed at the bottom of `MIDDLEWARE` so it
    runs first on the response chain, before any other middleware
    touches the 302. Related 403 silent-failure case deferred to
    `ISSUES.md`.

---

## Handed to future branches

- **Reactivation/cancel privilege confusion** — needs an
  `approved_at` field on `User` (or `is_approved` on `Employee`) to
  separate account approval from employment state. Currently both
  flows set `is_active = True`, which lets a Management user without
  `auth.change_user` approve pending accounts through employment
  restoration. See `ISSUES.md`.
- **CSP Phases 1 and 2.** Phase 1 (unsafe-inline) is a small win
  over Django's autoescape; Phase 2 (nonces + Alpine CSP build) is
  the real one. Own session. See `SECURITY_SWEEP.md` "CSP plan
  (deferred)".
- **Accounts test layout** (`accounts/tests.py` → `accounts/tests/`).
  Prerequisite for the deferred SEC-007 automated test.