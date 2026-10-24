# BUGREPORT

Living record of known bugs, suspected bugs, and deferred fixes.
Every entry: what it is, how it manifests, status (confirmed or
suspected), severity, location, fix direction, target session.

Update as bugs are found or resolved. When a bug is fixed, keep the
entry but move it to `## Fixed` at the bottom with the fixing commit.

---

## Confirmed live bugs

### BUG-001 — Split-branch `old_shifts = {}` mislabels notification email

- **Severity:** Low (email content only — no data loss, no crash)
- **Location:** `schedule/views.py`, `_handle_pattern_form_post`, the
  `else:` branch (split case)
- **Symptom:** When a manager saves a pattern that splits a covering
  pattern **and** changes cycle length **and** checks "notify," the
  diff baseline is `old_shifts = {}` instead of the covering pattern's
  shifts. Every week in the new pattern reports "OFF → new value,"
  mislabeling the pre-change schedule in the email.
- **Root cause:** Empty baseline. Note that the "obvious" fix —
  `old_shifts = covering.shifts` — is *worse*, because in the split
  case the covering pattern's `week_offset` indices don't align with
  the target's (see BUG-002). A naive index-by-index diff mislabels
  every change.
- **Fix direction:** Capture a calendar-aligned baseline before the
  transaction. The natural implementation reuses
  `_grid_weeks_for_form(employee, effective_from, cycle_weeks)` keyed
  by calendar week, then translate to `(week_offset, day)` for
  `_diff_pattern_shifts`. Pairs naturally with BUG-002.
- **Target:** Session 5.5

### BUG-002 — `_grid_weeks_for_form` cycle misalignment between prefill and edit target

- **Severity:** Medium (user edits land on the wrong week)
- **Status:** Suspected — needs manual verification in dev before
  claiming as confirmed
- **Location:** `schedule/views.py`, `_grid_weeks_for_form`; interacts
  with `_week_offset_for` and the save loop in
  `_handle_pattern_form_post`
- **Symptom:** For a multi-week pattern P starting on a week where
  `(week_start - CYCLE_EPOCH) % P.cycle_weeks != 0`, "Change from this
  week" prefills the form with P's offset 0 as "Week A", but the
  target pattern's offset for the current week is *not* 0. When the
  manager edits "Week A," the edit lands on a different calendar week
  than the one they were looking at.
- **Reproduction:** In dev, create a 2-week pattern starting one week
  off from `CYCLE_EPOCH`'s modulo. Use "Change from this week." Edit
  Week A hours. Check whether the change shows on the current week or
  the following week.
- **Why it hides:** Only triggers when `cycle_weeks > 1` *and* the
  current week's cycle offset ≠ 0. Single-week patterns never show it
  (offset always 0).
- **Fix direction:** Calendar-aware prefill. Map source weeks to
  calendar weeks (not cycle offsets), and translate back when saving.
  Same helper as BUG-001.
- **Target:** Session 5.5

### BUG-003 — Submitted grid values lost on validation errors

- **Severity:** Medium (user loses all typed edits on one bad cell)
- **Status:** Confirmed, deferred per user preference
- **Location:** `schedule/views.py`, every error-path
  `return _render_pattern_form(...)` in `_handle_pattern_form_post`
- **Symptom:** Manager types a full week of hours, hits Save, gets one
  bad-cell error ("end time must be after start time"). Form snaps
  back to the covering pattern's values. All typed edits are gone.
  Affects change, add, and the (planned) edit page alike.
- **Root cause:** `_pattern_form_context` supports `submitted_shifts`,
  but no caller passes it. Dead code.
- **Fix direction:** Before the grid-validation loop, collect every
  successfully-parsed `(week_offset, day) → (start, end)` pair into a
  dict of Shift-like objects (need `.start_time` / `.end_time`
  attributes so the template's `|time` filter works). Pass to every
  error-path `_render_pattern_form`. Half-broken cells (only one of
  start/end set) can't cleanly become Shift-like without either
  preserving raw text or breaking the `|time` filter — drop them; the
  error banner names which cell is bad.
- **Target:** housekeeping / when edit-page UX pressure makes it
  necessary

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

### BUG-006 — `_week_picker_options` may exclude the pattern's own `effective_from`

- **Severity:** Low (edge case; relevant to Session 6's edit page)
- **Status:** Suspected — verify at Session 6 start
- **Location:** `schedule/views.py`, `_week_picker_options`
- **Symptom:** The floor is `today - 180 days`. Any pattern whose
  `effective_from` predates that won't be in the `<option>` list. On
  the edit page (where the week picker is disabled and pre-set to the
  pattern's date), a `disabled` select with no matching option renders
  as the first option — displaying the wrong week as "the pattern's
  start."
- **Check at Session 6 start:** confirm no active pattern predates
  `today - 180d`; if any does, either widen `_week_picker_options` or
  inject the pattern's own date into the option list on the edit page.
- **Target:** Session 6

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

- **Severity:** Low (edge case; relevant to Session 6's edit page)
- **Status:** Verified not currently triggered (2026-10-23) — no pattern
  in prod has an `effective_from` older than `today - 180d`. Will
  re-surface when the first pattern ages past 180 days.
- **Location:** `schedule/views.py`, `_week_picker_options`
- **Symptom:** The floor is `today - 180 days`. Any pattern whose
  `effective_from` predates that won't be in the `<option>` list. On
  the edit page (where the week picker is pre-set to the pattern's
  date), a select with no matching option renders as the first option
  — displaying the wrong week as "the pattern's start."
- **Fix direction:** Superseded by UX-001 (calendar picker with
  `CYCLE_EPOCH` floor). Don't fix in isolation; fix as part of the
  week-picker rewrite.
- **Target:** the week-picker session (see UX-001)

---

## Fixed

(None yet — append entries here as bugs are resolved.)