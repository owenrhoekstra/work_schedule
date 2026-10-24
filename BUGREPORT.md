# BUGREPORT

Living record of known bugs, suspected bugs, and deferred fixes.
Every entry: what it is, how it manifests, status (confirmed or
suspected), severity, location, fix direction, target session.

Update as bugs are found or resolved. When a bug is fixed, keep the
entry but move it to `## Fixed` at the bottom with the fixing commit.

**Current snapshot:** Session 6 (pattern edit page) complete, pending
commit. Sessions 5.5, 6.5, 6.6, 7, 8, 9 pending. See "Target" on each
entry.

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
  Affects change and add. The edit page is now protected (see partial
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
  returns, so editors do not lose typed values there. Only fully-parsed
  cells are preserved; the cell whose validation failed falls back to
  blank.

### BUG-004 — `_identity_form.html` references missing `openDeactivate()`

- **Severity:** Low today (unreachable) — blocking for Session 7
- **Location:** `schedule/templates/schedule/partials/_identity_form.html`,
  "Set Last Day" button: `@click="openDeactivate()"`
- **Symptom:** No `openDeactivate()` method exists in any Alpine
  component. The form isn't currently included in
  `employee_defaults.html`, so the button never renders — but Session 7
  must wire this method (or convert the button to `onclick` controlling
  the modal directly, as `settings.html` does).
- **Target:** Session 7

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

Recorded so implementation and future reviews stay consistent.

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
   - **Why `effective_to` exists at all:** it's a pre-migration scaffold
     for the (much later) bulk-overrides feature, which will use a
     similar edit-or-split pattern. Until then, no UI sets it directly;
     the schedule resolver uses it to determine which pattern covers a
     given week. Don't add direct-edit UI for it.

3. **Delete confirmation.** Every destructive action requires a
   secondary confirmation. Prefer the modal pattern
   (`_delete_pattern_confirm.html` already exists in the repo). Browser
   `confirm()` is acceptable only as a last resort.

4. **Retroactive.** Confirmation required only when **editing an
   already-saved pattern whose `effective_from` is in the past**.
   Editing is destructive of written history. Creating a new pattern
   at this week does not need retroactive confirmation; it's the
   normal "change now" flow.

5. **Earliest-pattern guard.** The edit page hides the delete button
   when the pattern being edited is the employee's earliest. Server
   guard already exists in `delete_pattern`; keep it — hidden UI is
   not a permission.

6. **Prefill.** See separate discussion (deferred; scope TBD).

---

## UX / feature requests

### UX-001 — Week picker should be a calendar, not a dropdown

- **Severity:** Medium (UX friction, not a correctness bug)
- **Status:** Confirmed, deferred — user wants it eventually, not
  urgent, but the dropdown won't survive multi-year use
- **Location:** `schedule/views.py::_week_picker_options`;
  `schedule/templates/schedule/pattern_form.html` (week picker)
- **Current:** `<select>` populated by `_week_picker_options`, scoped to
  `max(employee.start_date, today-180d)` through
  `max(employee.last_day or today+365d, today+90d)`.
- **Problems:**
  - Dropdown scales badly past ~20 weeks (excessive scrolling).
  - The 180-day floor / 365-day ceiling are workarounds for that
    scaling — they exist because a dropdown can't hold unlimited
    options, not because the domain requires limits.
  - The floor silently excludes old patterns (see BUG-006).
  - Managers plan change visually ("three weeks from now, the week
    starting ___") — a calendar matches that mental model; a scrolling
    `<select>` does not.
- **Desired:** Inline calendar (or calendar modal) with days grouped
  into Mon–Sat visual bands, each band a clickable "week" cell. No
  artificial floor except `CYCLE_EPOCH` (earliest valid
  `effective_from`). No artificial ceiling — unlimited forward
  planning. Still Monday-aligned. Retroactive warnings continue to
  fire based on `effective_from < this_week_start`.
- **Notes:**
  - Any picker change should be uniform across change / add / edit
    pages.
  - Subsumes BUG-006.
  - Prefilled value on edit page must remain the pattern's own
    `effective_from` even after the picker rewrite.
- **Target:** own session after Session 6 ("week picker calendar").
  Call it Session 6.5 or Session 6-adjacent — TBD.

### UX-002 — General styling pass

- **Severity:** Low (cosmetic; no correctness impact)
- **Status:** Confirmed, deferred. First instance landed Session 6
  (Cancel-button focus rings on the retroactive and delete modals).
- **Scope:** App-wide. Known starting points:
  - Focus rings on dialog buttons — Safari's default blue ring is
    off-brand. Brand them with
    `focus:outline-none focus:ring-2 focus:ring-brand-coral focus:ring-offset-1`.
  - Native form controls (any surviving `<select>` / `<input>` that
    hasn't been styled by `_INPUT_CLASS` or an equivalent).
  - Focus states across all interactive elements — links, buttons,
    table rows.
  - Modal `.is-closing` animations — verify against Safari specifically
    (Safari's `<dialog>` positioning has quirks; `margin: auto` in
    `dialog.modal-animate` is the known mitigation if centering breaks).
  - Print view — verify color / B&W rendering on actual paper.
- **Target:** Session 9 (QA + ship) at the latest. Pull forward sooner
  if the friction becomes visible to end users.

---

## Deferred / out of scope

- Full prefill modal (week-by-week copy from a different pattern) —
  possibly its own session
- Bulk overrides (its own branch, built on the pattern-editing
  foundation)
- Moving an existing pattern's `effective_from` via the edit page
- Pattern end-date UI
- Reordering patterns
- Import / export of patterns
- Session 8's signal removal (`ensure_employee_has_pattern`)

### BUG-006 — `_week_picker_options` may exclude the pattern's own `effective_from`

- **Severity:** Low (edge case; partially mitigated)
- **Status:** Verified not currently triggered (2026-10-23) — no pattern
  in prod has an `effective_from` older than `today - 180d`. The edit
  page is now safe regardless: `_pattern_form_context` injects the
  pattern's own `effective_from` into `week_options` if it isn't in the
  base range. Change/add pages still rely on the 180-day floor and will
  silently omit very old weeks if a `?week=` link points there.
- **Location:** `schedule/views.py`, `_week_picker_options`
- **Fix direction:** Superseded by UX-001 (calendar picker with
  `CYCLE_EPOCH` floor). Don't fix in isolation; fix as part of the
  week-picker rewrite.
- **Target:** the week-picker session (see UX-001)

---

## Fixed

### FIXED-001 — Edit link restored on pattern history list

- **Fixed:** Session 6. `_saved_patterns.html` "Edit" link is now a
  real `<a>` to `pattern_edit`.
- **Follow-up:** delete URL was left at `/patterns/<uuid>/delete/`
  rather than the redesign doc's `/employees/<uuid>/patterns/<uuid>/delete/`.
  Cosmetic mismatch; can be aligned later.

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
- **Root cause:** Panel index in the form was treated as the target
  pattern's cycle offset, but cycle offset 0 is not calendar week
  `effective_from` when `effective_from` isn't congruent with
  `CYCLE_EPOCH`. Prefill showed the wrong calendar week; the save
  loop wrote edits to the wrong offset; the split branch's
  notification baseline was `{}`.
- **Fix:**
  - New `_cycle_offset(week_start, cycle_weeks)` — factored out of
    `_week_offset_for` so it can be called without a pattern instance.
  - New `_calendar_aligned_shifts(employee, effective_from, cycle_weeks)` —
    builds a baseline keyed by target offset from the actual calendar
    weeks the panels represent.
  - `_grid_weeks_for_form` now indexes panels by calendar week
    (`effective_from + 7*i`), pre-filling from whichever pattern
    covers that week.
  - Save loops in `_handle_pattern_form_post` and
    `_handle_pattern_edit_post` translate `(cal_offset, day)` →
    `(target_offset, day)` where
    `target_offset = (base_target_offset + cal_offset) % cycle_weeks`.
  - Split branch uses `_calendar_aligned_shifts` for `old_shifts`
    before mutating `covering.effective_to`.
  - When `cycle_weeks` shrinks, shifts at `week_offset >= new cycle`
    are deleted (they're unreachable under the new cycle).
- **Tests:** `schedule/tests/test_pattern_alignment.py` — prefill
  alignment, edit-in-place save, split-branch notification baseline.
- **Known limitation (not fixed):** changing `cycle_weeks` on an
  existing pattern reinterprets stored offsets — data at old offsets
  represents different calendar weeks under the new cycle. The
  prefill/save alignment is correct under the new semantics; existing
  data may be overwritten (grow) or deleted (shrink). Not currently
  surfaced in the UI. Follow-up if it bites.
