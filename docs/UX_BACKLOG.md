# UX backlog

Forward-looking UX and feature requests. Persistent across branches.
When an item is picked up for a session, it moves to that session's
plan and eventually into `bugs/FIXED.md` (if it was bug-shaped) or
`design/SESSIONS.md` (if it was design-y).

Items marked **Delivered** shipped in an earlier branch; their
follow-ups stay here. Open items await a session. The **Deferred**
section is branch-level "not doing this now" — some become future
sessions, some become separate branches.

---

## Delivered, follow-ups remaining

### UX-001 — Week picker calendar

- **Status:** Delivered Session 6.5.
- **Shipped:** Modal calendar with 7-day Mon–Sun bands, current-week
  ring, today dot, pre-start-date disabled, month/year navigation,
  12-month grid via month-name click, scrollable year list via
  year click. Self-contained Alpine component scoped to the dialog.
  Replaces the `<select>` week picker. `_week_picker_options`
  removed — resolves BUG-006 as a side effect.
- **Follow-up:** If the calendar ever feels "blind" (no visual cue of
  when existing patterns start), overlay subtle bands per pattern
  range. Skipped as not-yet-warranted complexity.

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
- **Follow-ups:**
  - Add Employee modal Cancel still dismisses without discard
    confirmation. Modal-in-modal UX is awkward; leave for now.
  - `_reactivate.html` still uses pre-`.modal-animate` inline style
    from settings.html. Extract and standardize when UX-004 lands.
  - Dirty-state guard: if the identity form has unsaved edits when the
    user triggers Set Last Day / Cancel deactivation, those
    independent POSTs navigate away and lose the edits. Revisit if
    end users complain.
  - "Change last day" flow was scoped out — the details page shows
    "Cancel deactivation" only. To change a scheduled date, cancel
    first, then set the new one. Revisit if that two-step flow
    becomes awkward.
  - Settings page's "Cancel deactivation" button does not pass
    `next`, so it still lands on settings_home. Fine for now; will
    be revisited when UX-004 lands.

---

## Open

### UX-002 — General styling pass

- **Severity:** Low (cosmetic)
- **Status:** Confirmed, deferred. Instances landed in Sessions 6, 7,
  7.5, 6.5, and 9 (focus rings on modals, calendar's Cancel button).
- **Scope:** App-wide.
  - Focus rings on dialog buttons — branded coral, not Safari's
    default blue.
  - Native form controls not yet touched by `_INPUT_CLASS` or
    equivalent.
  - Focus states across all interactive elements.
  - Modal `.is-closing` animations — verify against Safari (`margin:
    auto` in `dialog.modal-animate` is the known mitigation if
    centering breaks).
  - Print view — verify color / B&W rendering on actual paper.
- **Target:** whenever, no specific session.

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

### UX-005 — Pattern history: horizontal weeks + pagination

- **Severity:** Low-Medium (vertical bloat, worsens with history size
  and cycle length)
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
- **Notes:** The reading page's "Currently scheduled" card already
  uses Alpine-driven tab pagination for the current pattern; the same
  pattern can be reused here. Header dates (effective_from /
  last_week) stay on the collapsed row — no change to that part.

---

## Planned sessions

### Session 6.6 — Prefill modal

- **Status:** Planned, not yet scheduled.
- **Scope:** Week-by-week copy from a different pattern. Manager
  picks a source pattern and maps its weeks onto the new pattern's
  weeks, then continues editing from there.
- **Dependencies:** Session 6's edit-or-split save logic (done);
  Session 6.5's calendar picker (done).
- **Notes:** The blank-extra-weeks default from Session 9's "prefill
  dedupe" (FIXED-012) is the baseline state. The modal layers on top
  of that default rather than replacing it.

---

## Deferred / out of scope

- Moving an existing pattern's `effective_from` via the edit page
- Pattern end-date UI
- Reordering patterns
- Import / export of patterns
- Bulk overrides (its own branch, built on the pattern-editing
  foundation)
- Multi-tenancy (AGENTS.md covers the prep; not this app's near-term
  scope)