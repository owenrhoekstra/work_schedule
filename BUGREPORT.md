# BUGREPORT

Living record of known bugs, suspected bugs, and deferred fixes.
Every entry: what it is, how it manifests, status (confirmed or
suspected), severity, location, fix direction, target session.

Update as bugs are found or resolved. When a bug is fixed, keep the
entry but move it to `## Fixed` at the bottom with the fixing commit.

**Current snapshot:** Sessions 1–8, 5.5, 6.5, 7, 7.5 complete.
Session 9 (QA + ship) is closing out — CodeRabbit passes 1–5 applied.
One more CodeRabbit pass scheduled, then this document gets a
layout restructure, then merge. No confirmed live bugs remaining;
all tracked items are either fixed or in Deferred / out of scope.
See "Target" on each entry.

---

## Confirmed live bugs

_(None currently. All tracked bugs are either fixed or moved to
Deferred / out of scope below.)_

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

## Session 6.5 design decisions

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
4. **BUG-006 mitigated and its cause removed.** The old 180-day floor
   existed only because the `<select>` couldn't hold unlimited
   options. The calendar picker has no such limit; `_week_picker_options`
   and its fallback logic are gone.
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

## Session 8 design decisions

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

## BUG-003 / BUG-007 fix decisions

1. **BUG-003 (server-side):** grid validation collects all errors
   before re-rendering and stashes every successfully-parsed cell into
   `submitted_shifts` (a dict of `SimpleNamespace(start_time, end_time)`).
   The error re-render uses those values instead of the covering
   pattern's prefill. Parse-failed or half-parsed cells are dropped —
   no clean way to render them as a Shift-shaped object for the
   `|time` template filter. Invalid pairs (end <= start) ARE stashed
   so the user sees both values plus the error message and can just
   fix the failing side. Behavior is uniform across
   `_handle_pattern_form_post` (change / add) and
   `_handle_pattern_edit_post` (edit).
2. **BUG-007 (client-side):** a `valueCache` object inside the
   `_pattern_form_body.html` script IIFE snapshots visible time input
   values on `htmx:beforeRequest` when the cycle picker fires, and
   restores them from `htmx:afterSwap` into the fresh
   `#pattern-form-body`. Cache persists across multiple cycle changes
   so shrink-then-grow retains hidden weeks' values. Cleared on
   submit (capture-phase listener; server response becomes source of
   truth) and on week change (different context).
3. **Scope consciously limited** to time inputs. Notify checkbox and
   retroactive-confirmed hidden input reset on cycle-change re-render;
   leaving for a follow-up if the friction surfaces. Both are less
   severe than losing typed grid values.

---

## Session 9 fix decisions

1. **Dual-duty retroactive modal.** Retroactive save shows a single
   modal ("Save retroactive changes?") that acts as both the warning
   and the save confirmation. Confirm sets `retroactive_confirmed=1`
   AND `saveConfirmed` and submits directly — no second modal. Non-
   retroactive saves show the generic save confirmation modal instead.
   One modal per save attempt, chosen based on retroactivity.
2. **Confirmations on the pattern form.** Save always routes through
   a confirmation modal (`_confirm_save_pattern.html` or the
   retroactive modal). Cancel routes through `_confirm_discard.html`
   (previously a plain `<a href>` — no discard warning). Both via the
   `_pattern_form_body.html` submit interceptor and inline onclick.
3. **Truncated-pattern edit support.** A split can leave a pattern
   with `cycle_weeks > span_weeks`. The edit guard now rejects only
   growing past the span (`cycle_weeks > span_weeks AND cycle_weeks >
   pattern.cycle_weeks`); unchanged or reduced cycles are allowed.
   Companion prefill fix: `_grid_weeks_for_form` accepts an optional
   `pattern` argument; edit mode uses direct-pattern prefill so
   unchanged saves don't write next-pattern data into hidden offsets.
   The truncated-edit exception lives only in `_handle_pattern_edit_post`;
   `_handle_pattern_form_post` does not share it — see bullet 8.
4. **Prefill dedupe on cycle extension.** When target cycle is longer
   than source cycle, later panels would wrap to source offsets
   already prefilled into earlier panels; those duplicate panels are
   left blank. The user is extending the cycle — extra weeks are new
   territory. Skipped in edit mode (which uses direct prefill and
   can't duplicate).
5. **Reading-page range display shows Mon–Sun.** Collapsed history
   rows and the "Currently scheduled" card render
   `last_week + 6 days` (Sunday) instead of `last_week` (Monday), so a
   1-week pattern reads "Oct 19 through Oct 25" instead of "Oct 19
   through Oct 19". Banner copy still uses the Monday for
   "until Week of X" phrasing, where a week-starting reference is
   correct.
6. **Retroactive-guard error re-renders preserve grid values.** Grid
   parse runs before the retroactive guard in both handlers so the
   retroactive error re-render can pass `submitted_shifts` and keep
   the user's typed values. Pre-grid errors (effective_from parse,
   start_date_floor, span guard) can't preserve — the user is
   changing weeks/cycles anyway, and the client-side cache is cleared
   on that change.
7. **Hidden-week POST cells skipped in parse and save loops.** After
   the cycle-shrink HTMX swap, `week_2_*` / `week_3_*` inputs remain
   in the POST body even when `cycle_weeks=2`. Both `validated_edits`
   and `submitted_shifts` construction skip `cal_offset >= cycle_weeks`,
   and the save loop's modulo translation guards the same condition.
   Without this, the modulo mapping put those hidden cells back onto
   visible offsets 0 and 1 (empty = deleted, non-empty = overwrite).
8. **Target-span check on change/add.** `_handle_pattern_form_post`
   computes the target pattern's eventual `effective_to` (covering's
   `effective_to` for split/edit-in-place; next pattern's
   `effective_from` for new) and rejects `cycle_weeks > span_weeks`
   before opening the transaction. No `covering.cycle_weeks` exception
   — the truncated-edit path stays on `/patterns/<uuid>/`. Without
   this, a change at a 2-week-remaining span with `cycle_weeks=4`
   would create a pattern whose offsets 2 and 3 never display.

---

## UX / feature requests

### UX-001 — Week picker calendar

- **Status:** Delivered Session 6.5.
- **Shipped:** Modal calendar with 7-day Mon–Sun bands, current-week
  ring, today dot, pre-start-date disabled, month/year navigation,
  12-month grid via month-name click, scrollable year list via
  year click. Self-contained Alpine component scoped to the dialog.
  Replaces the `<select>` week picker. `_week_picker_options` removed
  — resolves BUG-006 as a side effect.
- **Follow-up:** If the calendar ever feels "blind" (no visual cue of
  when existing patterns start), overlay subtle bands per pattern
  range. Skipped as not-yet-warranted complexity.

### UX-002 — General styling pass

- **Severity:** Low (cosmetic)
- **Status:** Confirmed, deferred. Instances landed in Sessions 6, 7,
  7.5, 6.5, and 9 (focus rings on modals, calendar's Cancel button).
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
    complain.
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

### UX-005 — Pattern history: horizontal weeks + pagination

- **Severity:** Low-Medium (vertical bloat, worsens with history size
  and cycle length)
- **Status:** New, deferred
- **Location:** `schedule/templates/schedule/partials/_saved_patterns.html`
  (the "Full pattern history" disclosure on the reading page)
- **Current:** Each expanded pattern entry stacks week A / B / C / D
  vertically, 6 rows per week. A 4-week cycle is 24 rows per pattern;
  a history with 3+ patterns balloons fast. Mobile becomes
  unscrollable past one expanded entry.
- **Desired:**
  - **Multi-week cycles:** display weeks side-by-side (columns per
    week A | B | C | D) instead of stacked. Columns have the same
    day rows, so a 4-week cycle reads as a 6-row × 4-column grid
    instead of a 24-row stack.
  - **Mobile:** paginate — show one week at a time with tabs,
    mirroring the "Currently scheduled" card's tab pattern on the
    reading page.
  - **Desktop:** horizontal week layout is probably enough; if it
    still feels cramped with a 4-week cycle, tab pagination is
    acceptable there too.
  - **Single-week cycles:** unchanged — one grid, no tabs.
- **Notes:**
  - The reading page's "Currently scheduled" card already uses
    Alpine-driven tab pagination for the current pattern; the same
    pattern can be reused here.
  - Header dates (effective_from / last_week) stay on the collapsed
    row — no change to that part.
- **Target:** Session 9 (QA + ship) or its own quick-fix session.

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
- UX-004 (move employee interactions out of settings)

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
  remains.
- **Delete modal:** `_saved_patterns.html` used browser `confirm()`;
  `pattern_form.html`'s edit page had no confirmation at all. Both now
  share `_delete_pattern_confirm.html` via the `deletePatternModal`
  Alpine component (registered once, guarded by
  `window.__deletePatternModalRegistered`).
- **Focus rings:** Cancel buttons on both modals have
  `focus:outline-none focus:ring-2 focus:ring-brand-coral focus:ring-offset-1`.
- **Test fixes:** Assertions on `retroactive-confirm-modal` and
  `delete-pattern-modal` were matching JS string literals in the
  inline script. Narrowed to `id="retroactive-confirm-modal"` and
  `id="delete-pattern-modal"`.

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

### FIXED-007 — Session 6.5: calendar week picker

- **Fixed:** Session 6.5.
- **Replaces** the `<select>` week picker (and `_week_picker_options`)
  with a modal calendar:
  - 7-day week bands (Mon–Sun) — future-proofs for multi-tenancy,
    where tenants will choose their own work days.
  - Current-week highlight (ring), today's cell (dot).
  - Weeks before `employee.start_date` are disabled.
  - No ceiling and no 180-day floor — resolves BUG-006 as a side
    effect.
  - Month step via ◀ / ▶; month name opens a 12-month selector;
    year opens a scrollable year list.
  - Edit mode shows a static week label (no picker button, no modal).
- **Architecture:** self-contained Alpine component scoped to the
  dialog only — no cross-scope reactivity, same isolation strategy
  used to fix the retroactive-confirm modal in Session 6.
- **Integration:** picking a week writes `#effective-from`'s value,
  dispatches a native `change` event (HTMX fires the existing
  preview GET to `pattern_form_preview`), updates the trigger
  button's label client-side, closes the modal.
- **Removed:** `_week_picker_options` (dead after this change).
- **Tests:** `schedule/tests/test_week_picker.py`.

### FIXED-008 — Session 8: signal removal

- **Fixed:** Session 8.
- **Removed:** `ensure_employee_has_pattern` from `signals.py`.
  Employee creation no longer auto-creates a ShiftPattern. New hires
  have no schedule until a manager sets one up via `/schedule/add/`.
- **Factory:** `make_employee` defaults to `with_pattern=False`.
  Tests opt in explicitly via `with_pattern=True` or by passing
  `cycle_weeks=N` (passing cycle_weeks at all implies
  with_pattern=True, including cycle_weeks=1).
- **Reading page:** three distinct states — pattern exists, "Not
  scheduled this week" (history but no active coverage), "Not
  scheduled at all" (new hire, `Set up schedule` CTA). The
  distinction is exposed via `has_any_patterns` in
  `_employee_page_context`.
- **EmploymentPeriod signal stays.** Only pattern auto-creation
  removed.
- **Tests updated:** `test_home.py`, `test_models.py`,
  `test_pattern_edit.py`, `test_week_picker.py`, `test_overrides.py`,
  `test_views_edges.py`, `test_details.py` — all opt in where needed.
  `test_signals.py` unchanged (only tests EmploymentPeriod and
  User-sync).

### FIXED-009 — BUG-003: submitted grid values preserved on validation errors

- **Fixed:** Session 9 (pre-QA pass).
- **Location:** `schedule/views.py::_handle_pattern_form_post`,
  `schedule/views.py::_handle_pattern_edit_post`.
- **Fix:** Grid validation now collects ALL errors before
  re-rendering, and stashes every successfully-parsed cell in
  `submitted_shifts` (dict of `SimpleNamespace(start_time, end_time)`)
  keyed by `(cal_offset, day)`. The error re-render uses those values
  instead of covering-pattern prefill. Invalid pairs (end <= start)
  ARE stashed so the user sees both values plus the error message.
  Parse-failed or half-parsed cells are dropped — no clean way to
  render them as a Shift-shaped object for the `|time` template
  filter. Behavior uniform across change, add, and edit handlers.
- **Tests:** `test_pattern_forms.py::test_change_preserves_valid_cells_on_validation_error`,
  `test_pattern_forms.py::test_change_preserves_cells_after_first_error`,
  `test_pattern_edit.py::test_edit_preserves_valid_cells_on_error`.

### FIXED-010 — BUG-007: cycle-length changes preserve typed grid values

- **Fixed:** Session 9 (pre-QA pass).
- **Location:** `schedule/templates/schedule/partials/_pattern_form_body.html`
  (script).
- **Fix:** Client-side `valueCache` in the pattern form's script IIFE:
  - `htmx:beforeRequest` on `#cycle-weeks` → snapshot every visible
    time input's value keyed by input `name`.
  - `htmx:afterSwap` on `#pattern-form-body` → restore any input
    whose name is in the cache.
  - Cache persists across multiple cycle changes: shrinking hides
    weeks but their values stay cached; extending back restores them.
  - Cache cleared on submit (capture phase; server response becomes
    source of truth).
  - Cache cleared on `#effective-from` change (different week =
    different context).
- **Manual verification only** — pure client-side JS, no Django test
  coverage possible with the current test stack.
- **Scope consciously limited** to time inputs. Notify checkbox and
  retroactive-confirmed hidden input reset on cycle-change re-render.

### FIXED-011 — Pattern form Save and Cancel confirmations

- **Fixed:** Session 9 (pre-QA pass).
- **New `_confirm_save_pattern.html`.** Every non-retroactive Save on
  the pattern writing form (change / add / edit) routes through this
  confirmation modal. Cancel on the modal aborts without submitting.
- **Retroactive save gets its own dual-duty modal.**
  `_retroactive_confirm.html` serves as both the retroactive warning
  AND the save confirmation. Confirm sets both
  `retroactive_confirmed=1` and `saveConfirmed` and submits directly
  — one modal, one click. Non-retroactive saves use
  `_confirm_save_pattern.html` instead. No chained modals.
- **Cancel on pattern form** routes through `_confirm_discard.html`
  (previously a plain `<a href>` with no warning).
- **Wiring:** `_pattern_form_body.html` submit interceptor routes to
  the correct modal based on `is_retroactive` and the current
  `retroactive_confirmed` state. `data-save-confirmed` flag on
  `#pattern-form-body` bypasses the interceptor on the final submit.
- **Tests:** modal-presence assertions in `test_pattern_forms.py` and
  `test_pattern_edit.py`.

### FIXED-012 — CodeRabbit pass 1: accessibility + timezone + truncated-pattern guard

- **Fixed:** Session 9 (CodeRabbit pass).
- **Accessibility:**
  - `_confirm_save_pattern.html` dialog gets `aria-labelledby` pointing
    at its `<h2>` (which gains a matching `id`).
  - `_week_picker.html` dialog gets `aria-label="Choose a week"`.
    Each week-band button gets `:aria-label="week.label"` —
    `buildWeek` now produces `"Week of Oct 5 to Oct 11"` labels.
- **Test stability:** `test_details.py` uses `timezone.localdate()`
  instead of `date.today()` throughout (per AGENTS.md — prevents
  midnight flake when server timezone differs from `TIME_ZONE`).
- **Truncated-pattern edit fix:**
  - Cycle-length guard in `_handle_pattern_edit_post` now rejects
    only `cycle_weeks > span_weeks AND cycle_weeks > pattern.cycle_weeks`.
    Unchanged or reduced cycles on a truncated pattern are allowed —
    the user should be able to shrink to fit, or save minor edits
    without being forced to shrink.
  - Companion prefill fix: `_grid_weeks_for_form` accepts optional
    `pattern` argument. When set (edit mode) it pulls from the
    pattern's own cycle offsets instead of calendar-week lookup.
    `_pattern_form_context` and `_render_pattern_edit_form` thread
    `pattern` through; `pattern_form_preview` resolves the pattern
    from `(employee, effective_from)` in edit mode so HTMX cycle
    changes also use the direct path.
  - Without the prefill fix, relaxing the guard alone would have
    written next-pattern data into hidden offsets on unchanged saves.
- **Prefill dedupe on cycle extension (change/add mode only):**
  when target cycle exceeds source cycle, later panels that would
  wrap to already-prefilled source offsets are left blank. The user
  is extending the cycle; extra weeks are new territory. Not
  applicable in edit mode (direct prefill can't duplicate).
- **Tests:** `test_pattern_edit.py::TruncatedPatternEditTests`,
  `test_pattern_alignment.py::PrefillDedupeTests`.

### FIXED-013 — Pattern history shows Mon-Sun range

- **Fixed:** Session 9 (CodeRabbit pass).
- **Symptom:** Collapsed rows in "Full pattern history" (and the
  "Currently scheduled" card's `through` line) rendered Mon-Mon. A
  1-week pattern read "Effective from October 19, 2026 through
  October 19, 2026" — identical start and end — because `last_week`
  is the Monday of the last covered week (derived from the
  exclusive `effective_to`).
- **Fix:** `_employee_page_context` now exposes `last_week_end` (per
  history entry) and `current_last_week_end` (for the current
  pattern card), both computed as `last_week + 6 days` — the Sunday
  of the last covered week.
  - `_saved_patterns.html`: uses `entry.last_week_end`.
  - `employee_defaults.html`: uses `current_last_week_end`, and the
    wording changes from "through Week of {{ sunday }}" to
    "through {{ sunday }}" — a Sunday isn't a week start.
  - `_last_week_of` unchanged: banner copy still uses the Monday for
    "until Week of X" phrasing, where a week-starting reference is
    correct.
- **Tests:** `test_employee.py::test_pattern_history_displays_mon_sun_range`,
  `test_employee.py::test_current_pattern_card_displays_sun_end`.

### FIXED-014 — Favicon MIME type

- **Fixed:** Session 9 (CodeRabbit pass).
- **Symptom:** `<link rel="icon" type="image/x-icon" href="...favicon.svg">`
  in `base.html` and `print_schedule.html`. Browsers worked anyway
  because they sniff the actual content, but the declared type was
  wrong.
- **Fix:** `image/x-icon` → `image/svg+xml` where the `href` points
  at `favicon.svg`. Files referencing `favicon.ico` left alone.
- **Touched:** `templates/base.html`,
  `schedule/templates/schedule/print_schedule.html`.

### FIXED-015 — BUG-005: restore_local_db.py hardening

- **Fixed:** Session 9 (CodeRabbit pass). Bundled with PGPASSWORD
  injection (same file, one touch).
- **PGPASSWORD:** Injected into the psql child environment from
  `POSTGRES_PASSWORD` so the restore can authenticate non-
  interactively against a password-protected server. Child env only
  — `os.environ` not mutated (would leak the credential to every
  subsequent subprocess). Skipped when `POSTGRES_PASSWORD` is unset
  or empty so trust/peer auth for local dev is unaffected.
- **Atomicity:** psql now runs with `-v ON_ERROR_STOP=1` and
  `--single-transaction`. Any SQL error aborts the restore and rolls
  back the whole transaction. Partial restores become impossible.
  Caveat: dumps containing non-transactional statements
  (`CREATE INDEX CONCURRENTLY`, `ALTER SYSTEM`) will refuse to
  restore — a legitimate failure to surface, not to paper over.
- **`.psqlrc` isolation:** `-X` added so a user's `~/.psqlrc` can't
  silently override `ON_ERROR_STOP`.
- **Error visibility:** psql's stderr no longer captured — errors
  stream to the terminal live with psql's full context.
- **Return-code checking:** both subprocesses waited on and checked.
  Order is psql-first: under `ON_ERROR_STOP`, psql's failure causes
  producer's SIGPIPE, so reporting producer first would misattribute
  the failure. If psql succeeds but producer fails, that's the
  silent-truncation case and gets its own message.
- **Follow-up:** `reset_local_db.py` (invoked by this script) may
  also need PGPASSWORD if it drops/creates via psql over TCP. Not in
  scope for this fix (finding excluded it explicitly). Address when
  the file next needs work.

### FIXED-016 — Retroactive-guard error re-render preserves grid values

- **Fixed:** Session 9 (CodeRabbit pass).
- **Symptom:** With the dual-duty retroactive modal, the server-side
  retroactive guard rarely fires. When it did (JS bypassed,
  interceptor failure), the error re-render dropped the user's typed
  grid values — the same data-loss class as BUG-003, but on a
  different error path.
- **Fix:** In both `_handle_pattern_form_post` and
  `_handle_pattern_edit_post`, grid parsing moved BEFORE the
  retroactive guard. The retroactive error return now includes
  `submitted_shifts=submitted_shifts`, preserving the user's typed
  values on the error re-render.
- **Not preserved** on: effective_from parse failure, start_date_floor
  rejection, span guard rejection. Those are pre-grid-context errors
  — the user is picking a different week or cycle length, and the
  client-side cache is cleared on that change anyway.
- **Tests:** `test_pattern_forms.py::test_retroactive_guard_preserves_typed_grid_values`,
  `test_pattern_edit.py::test_retroactive_guard_preserves_typed_grid_values`.

### FIXED-017 — CodeRabbit pass 2: aria labels, deactivation redirect, restore pre-flight

- **Fixed:** Session 9 (CodeRabbit pass).
- **Accessibility (aria-labelledby on five modals):**
  - `_cancel_deactivation_confirm.html` → `aria-labelledby="cancel-deactivation-confirm-title"`.
  - `_confirm_discard.html` → `aria-labelledby="confirm-discard-title"`.
  - `_confirm_save_details.html` → `aria-labelledby="confirm-save-details-title"`.
  - `_deactivate.html` → `aria-labelledby="deactivate-title"`.
  - `_retroactive_confirm.html` → `aria-labelledby="retroactive-confirm-title"`.
  - Each h2 receives the matching `id`. Screen readers announce the
    title when the dialog opens.
- **`settings_deactivate_employee` redirect fallback:** When
  `is_immediate` (last_day in the past), the redirect target is
  always `settings_home` regardless of the `next` POST field. The
  reading page's filter excludes `last_day < today`, so honouring
  `next=employee_defaults` on an immediate deactivation would 404.
  Non-immediate deactivations still honour `next` — the reading page
  works for future-dated last days.
- **`restore_local_db.py` pre-flight checks:** Both run BEFORE the
  destructive reset, so a broken environment or corrupt backup
  leaves the current DB untouched.
  - `shutil.which("psql")` — refuses to reset if psql is missing.
  - `shutil.which("gunzip")` for .gz files — refuses if gunzip is
    missing.
  - `gunzip -t` on .gz files — verifies the entire compressed stream
    decompresses cleanly before anything is dropped. Catches the
    silent-truncation case that `--single-transaction` cannot: if
    gunzip dies mid-stream, psql sees EOF and commits whatever it
    received. `gzip -t` closes that gap.
  - Plain `.sql` files can't be pre-validated; the `producer_rc` check
    at the end remains as a belt-and-braces for those.
- **Tests:** `test_details.py::DeactivationRedirectTests::test_immediate_deactivation_overrides_employee_defaults_target`
  plus a companion for the future case.
- **Corrected safety documentation (follow-up):**
  `restore_local_db.py`'s module docstring previously overstated
  pre-flight protection. It now explicitly separates:
  - What pre-flight catches: missing tools (psql/gunzip) and corrupt
    .gz files. Current DB untouched in those cases.
  - What it does NOT catch: invalid SQL. Reset drops and recreates
    the DB before psql runs; if psql then rejects the dump,
    `--single-transaction` rolls back the restore portion, but the
    database stays empty. Pre-restore data is gone regardless.
  - Recommended practice: back up before running if post-reset
    failure would be costly.
  - psql failure exit message updated to tell the user their DB is
    now empty — the previous message ("psql exited with code N")
    was accurate but omitted the state consequence.

### FIXED-018 — Hidden-week POST cells cannot overwrite visible offsets

- **Fixed:** Session 9 (CodeRabbit pass 3).
- **Severity:** Medium (silent data loss in a routine flow; also a
  crafted-POST attack surface).
- **Symptom:** When shrinking `cycle_weeks` (e.g. 4 → 2), the save
  loops iterated all `MAX_CYCLE_WEEKS` `validated_edits` entries and
  mapped `cal_offset` back to a target offset via modulo. A
  `cal_offset` beyond `cycle_weeks - 1` (e.g. 2 when cycle_weeks=2)
  mapped onto a *visible* target offset (0), and applied whatever
  value was in the hidden cell. When the hidden cell was empty —
  which is the normal case, since the browser still submits
  `week_2_*` / `week_3_*` inputs after an HTMX cycle swap — the save
  loop **deleted** offsets 0 and 1. Users shrinking a 4-week pattern
  to 2 lost *all four* weeks, not just the two being discarded.
- **Also:** A crafted POST with `cycle_weeks=2` and weeks 0–3 all
  filled would overwrite week 0's data with week 2's via the same
  modulo collision.
- **Fix:** Both `_handle_pattern_form_post` and
  `_handle_pattern_edit_post` now skip `cal_offset >= cycle_weeks`
  in the parse loop (avoids surfacing errors for cells the user
  can't see) and in the save loop (defense in depth). Cells outside
  the visible range never reach the DB-write step. Cycle-shrink
  orphan deletion still removes offsets >= new cycle via the existing
  `Shift.objects.filter(pattern, week_offset__gte=cycle_weeks).delete()`
  path.
- **Existing test bug:** `test_reduced_cycle_save_allowed` passed
  before this fix because it only asserted offsets ≥ 2 were gone,
  never that offsets 0 and 1 survived. Extended to assert both.
- **Tests:**
  - `test_pattern_edit.py::TruncatedPatternEditTests::test_reduced_cycle_save_allowed`
    (extended).
  - `test_pattern_edit.py::TruncatedPatternEditTests::test_crafted_post_with_hidden_weeks_cannot_overwrite_visible`
    (new).
  - `test_pattern_forms.py::PatternFormViewTests::test_crafted_post_with_hidden_weeks_ignored`
    (new). Anchors `effective_from` at `settings.CYCLE_EPOCH` so
    `base_target_offset=0`, panel N maps to offset N, and the
    assertions name offsets by their panel letter. Non-congruent
    `effective_from` (e.g. arbitrary dates) flips the mapping and
    would make offset-by-panel-name assertions unreliable — the
    `TruncatedPatternEditTests.setUp` version already anchors at
    `CYCLE_EPOCH`, so it was unaffected.

### FIXED-019 — Week picker trigger's `data-selected` kept in sync

- **Fixed:** Session 9 (CodeRabbit pass 4).
- **Severity:** Low (cosmetic — picker highlights wrong week on
  reopen; no data corruption).
- **Symptom:** After picking a week via the calendar modal, reopening
  the picker highlighted the *previous* week, not the just-picked
  one. `openFromTrigger` reads `button.dataset.selected` for the
  initial `selectedISO`, and `pickWeek` updated `trigger.textContent`
  but not `trigger.dataset.selected`. The trigger's label and the
  picker's highlighted week could therefore disagree.
- **Fix:** `pickWeek` also sets `trigger.dataset.selected = iso`.
  Both the visible label and the attribute used for re-opening now
  follow the current selection.
- **Manual verification only** — pure client-side JS.

### FIXED-020 — Target-span check on change/add + `cat` pre-flight

- **Fixed:** Session 9 (CodeRabbit pass 5).
- **Finding 1 — target-span validation:** `_handle_pattern_form_post`
  now rejects `cycle_weeks > span_weeks` before the transaction,
  where span derives from the target pattern's eventual
  `effective_to` (covering's `effective_to` for edit-in-place and
  split, next pattern's `effective_from` for new). Without this,
  `/schedule/change/` could create a pattern whose extra cycle
  offsets sit past its own `effective_to` and never display — the
  user thinks they scheduled 4 weeks, only 2 render.
  - No `covering.cycle_weeks` exception. The truncated-pattern
    edit exception lives in `_handle_pattern_edit_post`
    (FIXED-012) and is reachable via `/patterns/<uuid>/`. Users
    editing a truncated pattern from `/schedule/change/` are told
    to shrink.
  - `submitted_shifts` preserved on the error re-render — typed
    values survive the rejection, same class as FIXED-009/016.
  - `covering = _pattern_for_week(...)` computed before the
    transaction; branch logic inside the transaction uses the
    pre-captured reference. No behavior change inside the
    transaction beyond the removal of the duplicate assignment.
  - Tests:
    `test_pattern_forms.py::test_change_rejects_cycle_larger_than_target_span`,
    `test_change_accepts_cycle_equal_to_target_span`,
    `test_change_new_pattern_accepts_cycle_within_next_pattern`,
    `test_change_new_pattern_rejects_when_next_is_too_close`.
- **Finding 2 — `cat` pre-flight:** `restore_local_db.py` now checks
  `shutil.which("cat")` for plain `.sql` dumps (the `.gz` path was
  already checking `gunzip`). If `cat` is missing, the script exits
  before the destructive reset rather than after. Docstring and
  pre-flight scope comment updated to name both streaming tools.