# BUGREPORT

Living record of known bugs, suspected bugs, and deferred fixes.
Every entry: what it is, how it manifests, status (confirmed or
suspected), severity, location, fix direction, target session.

Update as bugs are found or resolved. When a bug is fixed, keep the
entry but move it to `## Fixed` at the bottom with the fixing commit.

**Current snapshot:** Sessions 1–7.5 complete. Sessions 6.5, 6.6, 8,
9 pending. See "Target" on each entry.

---

## Confirmed live bugs

### BUG-003 — Submitted grid values lost on validation errors

- **Severity:** Medium (user loses all typed edits on one bad cell)
- **Status:** Confirmed, deferred per user preference
- **Location:** `schedule/views.py`, every error-path
  `return _render_pattern_form(...)` in `_handle_pattern_form_post`
- **Symptom:** Manager types a full week of hours, hits Save, gets one
  bad-cell error ("end time must be after start time"). Form snaps
  back to the covering pattern's values. All typed edits are gone.
  Affects change and add. The edit page is protected (see partial
  fix below).
- **Root cause:** `_pattern_form_context` supports `submitted_shifts`,
  but `_handle_pattern_form_post` never passes it on error paths.
- **Fix direction:** Before the grid-validation loop, collect every
  successfully-parsed `(week_offset, day) → (start, end)` pair into a
  dict of Shift-like objects (need `.start_time` / `.end_time`
  attributes so the template's `|time` filter works). Pass to every
  error-path `_render_pattern_form`. Half-broken cells (only one of
  start/end set) can't cleanly become Shift-like without either
  preserving raw text or breaking the `|time` filter — drop them; the
  error banner names which cell is bad.
- **Target:** housekeeping / when change/add UX pressure makes it
  necessary
- **Partial fix:** the pattern edit page
  (`_handle_pattern_edit_post`) passes `submitted_shifts` on error
  returns. Only fully-parsed cells are preserved; the cell whose
  validation failed falls back to blank.

### BUG-005 — `restore_local_db.py` lacks `--single-transaction` / `ON_ERROR_STOP`

- **Severity:** Low (dev-only script; would be data-integrity if ever
  used in prod)
- **Status:** Confirmed, deferred per user
- **Location:** `scripts/restore_local_db.py`
- **Symptom:** If the psql restore fails partway, the DB is left in a
  partial state. Errors on stderr don't stop the pipeline; producer
  failures may be masked by the consumer's exit code.
- **Fix direction:** Pass `-v ON_ERROR_STOP=1` and
  `--single-transaction` to psql, remove stderr capture so errors reach
  the terminal, wait for both processes, check `producer.returncode`
  before `psql.returncode`, exit with the relevant command + status.
- **Target:** whenever the script graduates to prod

---

## Session 6 design decisions

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

6. **Prefill.** See separate discussion (deferred; scope TBD — Session
   6.6).

---

## Session 7 design decisions

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
   `employee_defaults` → reading page; anything else → `settings_home`.
   Whitelist; no arbitrary URL redirects.
6. **`_confirm_discard.html` is the standard cancel-with-unsaved-state
   pattern.** Any Cancel button that would abandon edits routes through
   it via `openConfirmDiscardModal(href)`.

---

## Session 7.5 design decisions

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

## UX / feature requests

### UX-001 — Week picker should be a calendar, not a dropdown

- **Severity:** Medium (UX friction, not a correctness bug)
- **Status:** Confirmed, deferred
- **Location:** `schedule/views.py::_week_picker_options`;
  `schedule/templates/schedule/pattern_form.html`
- **Current:** `<select>` populated by `_week_picker_options`, scoped
  to `max(employee.start_date, today-180d)` through
  `max(employee.last_day or today+365d, today+90d)`.
- **Problems:**
  - Dropdown scales badly past ~20 weeks (excessive scrolling).
  - The 180-day floor / 365-day ceiling are workarounds for that
    scaling, not domain-required limits.
  - The floor silently excludes old patterns (see BUG-006).
  - Managers plan change visually — a calendar matches that mental
    model; a `<select>` does not.
- **Desired:** Inline calendar (or calendar modal) with days grouped
  into Mon–Sat visual bands, each band a clickable "week" cell. No
  artificial floor except `CYCLE_EPOCH`. No artificial ceiling.
  Monday-aligned. Retroactive warnings fire based on
  `effective_from < this_week_start`.
- **Notes:** Uniform across change / add / edit pages. Subsumes
  BUG-006. Prefilled edit-page value = the pattern's own
  `effective_from`.
- **Target:** Session 6.5.

### UX-002 — General styling pass

- **Severity:** Low (cosmetic)
- **Status:** Confirmed, deferred. Instances landed in Sessions 6, 7,
  and 7.5 (focus rings on retroactive / delete / deactivate / discard /
  cancel-deactivation / save-details modals).
- **Scope:** App-wide.
  - Focus rings on dialog buttons — branded coral, not Safari's default
    blue.
  - Native form controls not yet touched by `_INPUT_CLASS` or
    equivalent.
  - Focus states across all interactive elements.
  - Modal `.is-closing` animations — verify against Safari (`margin:
    auto` in `dialog.modal-animate` is the known mitigation if
    centering breaks).
  - Print view — verify color / B&W rendering on actual paper.
- **Target:** Session 9 (QA + ship) at the latest.

### UX-003 — Employee-UX polish

- **Status:** Delivered Session 7.5.
- **Shipped:**
  - Edit CTA moved into Employee card on reading page (small filled
    coral button, right-aligned, card footer).
  - Scheduled-deactivation banner on `/details/` with current last-day
    visible.
  - Cancel deactivation button + confirmation modal on `/details/`
    when `last_day` is set.
  - Save details confirmation modal (always shown).
- **Follow-ups deferred from Session 7.5:**
  - Add Employee modal Cancel still dismisses without discard
    confirmation. Modal-in-modal UX is awkward; leave for now.
  - `_reactivate.html` still uses pre-`.modal-animate` inline style
    from settings.html. Extract and standardize when UX-004 lands.
  - Dirty-state guard: if the identity form has unsaved edits when the
    user triggers Set Last Day / Cancel deactivation, those independent
    POSTs navigate away and lose the edits. Revisit if end users
    complain; the modal's Cancel path stays on the page so the hazard
    is smaller than it first looks.
  - "Change last day" flow was scoped out — the details page shows
    "Cancel deactivation" only. To change a scheduled date, cancel
    first, then set the new one. Revisit if that two-step flow
    becomes awkward.
  - Settings page's "Cancel deactivation" button does not pass
    `next`, so it still lands on settings_home. Fine for now; will be
    revisited when UX-004 lands.

### UX-004 — Move employee interactions out of settings (philosophy)

- **Status:** Philosophy only, not scheduled.
- **Principle:** Settings should be reserved for tenant-level config
  (titles, roles, and future tenant-level actions). Employee
  interactions should live near the employee context — not mixed in
  with tenant config in one long page.
- **Current state:** Settings currently holds Active employees table,
  Former employees table, Titles, Roles. The first two are the
  targets for relocation.
- **Possible shapes (undecided):**
  - Dedicated `/employees/` page linked from nav.
  - Former employees at `/employees/former/`, linked from settings.
  - "Show former employees" toggle on the home schedule.
- **Not tackled now.** Recorded so future sessions don't re-litigate
  the philosophy.

---

## Deferred / out of scope

- Full prefill modal (week-by-week copy from a different pattern) —
  Session 6.6
- Bulk overrides (its own branch, built on the pattern-editing
  foundation)
- Moving an existing pattern's `effective_from` via the edit page
- Pattern end-date UI
- Reordering patterns
- Import / export of patterns
- Session 8's signal removal (`ensure_employee_has_pattern`)
- UX-004 (move employee interactions out of settings)

### BUG-006 — `_week_picker_options` may exclude the pattern's own `effective_from`

- **Severity:** Low (edge case; partially mitigated)
- **Status:** Verified not currently triggered (2026-10-23) — no pattern
  in prod has an `effective_from` older than `today - 180d`. The edit
  page is safe regardless: `_pattern_form_context` injects the
  pattern's own `effective_from` into `week_options` if it isn't in the
  base range. Change/add pages still rely on the 180-day floor and
  will silently omit very old weeks if a `?week=` link points there.
- **Location:** `schedule/views.py`, `_week_picker_options`
- **Fix direction:** Superseded by UX-001.
- **Target:** Session 6.5 (see UX-001).

---

## Fixed

### FIXED-001 — Edit link restored on pattern history list

- **Fixed:** Session 6.
- **Follow-up:** delete URL was left at `/patterns/<uuid>/delete/`
  rather than `/employees/<uuid>/patterns/<uuid>/delete/`. Cosmetic;
  can be aligned later.

### FIXED-002 — Retroactive and delete confirmation modals wired

- **Fixed:** Session 6.
- **Retroactive modal:** Alpine `@click` on the Save button was not
  reliably invoking `handleSave` — physical clicks didn't fire the
  handler, though programmatic calls did. Replaced with a native
  `submit` interceptor on `document` plus inline `onclick` handlers
  on the modal's Cancel/Confirm buttons. No Alpine scope dependency
  remains; opening the modal, confirming, and dismissing are all plain
  DOM functions.
- **Delete modal:** `_saved_patterns.html` used browser `confirm()`;
  `pattern_form.html`'s edit page had no confirmation at all. Both now
  share `_delete_pattern_confirm.html` via the `deletePatternModal`
  Alpine component (registered once, guarded by
  `window.__deletePatternModalRegistered`).
- **Focus rings:** Cancel buttons on both modals have
  `focus:outline-none focus:ring-2 focus:ring-brand-coral focus:ring-offset-1`
  instead of Safari's default blue ring (first instance of UX-002).
- **Test fixes:** Assertions on `retroactive-confirm-modal` and
  `delete-pattern-modal` were matching JS string literals in the
  inline script, causing false positives / negatives. Narrowed to
  `id="retroactive-confirm-modal"` and `id="delete-pattern-modal"`.

### FIXED-003 — Calendar alignment between prefill, save, and notification baseline

- **Fixed:** Session 5.5. Resolved BUG-001 and BUG-002.
- **Fix:** New `_cycle_offset(week_start, cycle_weeks)`; new
  `_calendar_aligned_shifts(employee, effective_from, cycle_weeks)`;
  `_grid_weeks_for_form` indexes panels by calendar week
  (`effective_from + 7*i`) not target offset; save loops translate
  `(cal_offset, day)` → `(target_offset, day)` via
  `(base_target_offset + cal_offset) % cycle_weeks`; split-branch
  `old_shifts` uses calendar alignment; cycle-shrink deletes orphan
  shifts.
- **Tests:** `schedule/tests/test_pattern_alignment.py`.
- **Known limitation:** changing `cycle_weeks` on an existing pattern
  reinterprets stored offsets. Prefill/save are correct under the new
  semantics; existing data may be overwritten (grow) or deleted
  (shrink). Not surfaced in the UI. Follow-up if it bites.

### FIXED-004 — Details page, deactivate modal standardization, discard confirmation

- **Fixed:** Session 7.
- **New `/details/` page** at `employees/<uuid>/details/`, gated on
  `@management_required`. Reading page read-only; identity edits and
  deactivation live here.
- **`employee_defaults` POST dispatch removed.**
- **`_deactivate.html` extracted from settings.html.** Self-contained,
  `.modal-animate`, `window.openDeactivateModal(button)`, honours
  `data-next`. Settings.html's inline duplicate removed.
- **`_confirm_discard.html`** new reusable modal. Wired on
  `_identity_form.html` and `_pattern_form_body.html`.
- **`settings_deactivate_employee`** reads `next` field:
  `employee_defaults` → reading page; anything else → `settings_home`.
- **`make_manager_user` factory** extended with `change_employee` and
  `delete_employee`.
- **Tests:** `schedule/tests/test_details.py`.

### FIXED-005 — BUG-004 (`_identity_form.html` referenced missing `openDeactivate()`)

- **Fixed:** Session 7. `_identity_form.html` uses
  `onclick="openDeactivateModal(this)"` from the extracted
  `_deactivate.html`. No Alpine component dependency.

### FIXED-006 — Session 7.5: employee-UX polish

- **Fixed:** Session 7.5.
- **Edit CTA on reading page** moved from the identity card header
  (subtle text link) to a small filled coral button inside the card
  footer. Right-aligned, scoped label ("Edit employee"). Gated on
  `is_management`.
- **Scheduled-deactivation banner** on `/details/`: when `last_day`
  is set, a coral-toned banner above the form fields names the date
  and explains "Off from the following day." The footer swaps
  [Set Last Day] → [Cancel deactivation]. Both buttons gated on
  `perms.schedule.delete_employee`, consistent with the existing
  deactivate gate.
- **Cancel deactivation modal** — new
  `_cancel_deactivation_confirm.html`. Native-button pattern, no
  Alpine. Confirm submits the hidden `#cancel-deactivation-form`
  (sibling of the identity form; HTML forms cannot nest) which POSTs
  to `settings_cancel_deactivation` with `next=employee_details`.
- **Save details confirmation modal** — new
  `_confirm_save_details.html`. Always shown (user preference for
  explicit action on every save; revisit if noisy). Submit
  interceptor on `#identity-form`, native button confirm, flag-based
  re-submit.
- **`settings_cancel_deactivation`** now honours `next` POST field
  (whitelisted): `employee_details` → details page,
  `employee_defaults` → reading page, anything else → settings_home.
- **Tests:** `DetailsScheduledDeactivationTests`,
  `CancelDeactivationNextTests` in `schedule/tests/test_details.py`.