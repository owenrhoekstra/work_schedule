# Issues

Persistent queue of items to tackle in a future branch.

## Model

- **Scope:** follow-ups flagged on a branch (usually from `FIXED.md`
  entries), plus items from `UX_BACKLOG.md` that have "matured" —
  i.e. you've decided they're worth a session rather than just
  a wishlist entry.
- **Lifecycle:** items stay here until a branch picks them up. When
  a branch starts work on an item, it moves **out of here** and
  **into** that branch's `worklog/BUGREPORT.md` (bug-shaped) or
  `UX_BACKLOG.md` (UX-shaped), where it flows through the normal
  branch lifecycle.
- **Not GitHub Issues.** This file is the tracking surface. If you
  ever need external visibility (team, stakeholders), mirror
  selectively — but don't force that ceremony on yourself now.
- **Ordering:** within each section, roughly by priority then age.
  No ID scheme — reference the source (FIXED-###, UX-###) as a
  breadcrumb, but each item must stand on its own.

---

## Open

### Cycle-length change reinterprets stored offsets

- **Origin:** FIXED-003 known limitation.
- **Problem:** Changing `cycle_weeks` on an existing pattern
  reinterprets that pattern's stored shifts. Prefill and save are
  correct under the new cycle semantics, but "correct" means data
  at the old cycle's offsets now represents different calendar
  weeks. Shrinking a 4-week pattern to 2 silently deletes weeks C
  and D. Growing 1 → 4 leaves weeks B–D empty (the "blank extra
  weeks" default from FIXED-012).
- **Not currently surfaced.** No UI warns the manager that the
  semantic shift will reinterpret old data.
- **Possible directions:**
  - Warn before applying a cycle-length change on a saved pattern,
    naming the specific weeks that will be reinterpreted.
  - Offer a "preserve old data" mapping when the new cycle can
    accommodate the old offsets (e.g. 2 → 4 keeps A and B, leaves
    C and D blank — already the current behavior; 4 → 2 loses C
    and D — could prompt).
  - Leave as-is and accept the semantics.
- **Priority:** Low unless it bites a real user. The current
  behavior is documented; the friction is silent data loss on a
  destructive operation, which is exactly the class of thing worth
  surfacing eventually.

### Target-span live hint on the cycle picker

- **Origin:** FIXED-012 / FIXED-020 target-span work.
- **Problem:** When the target pattern's span (weeks until the next
  pattern, or to the covering pattern's `effective_to`) is smaller
  than the requested `cycle_weeks`, the server rejects on Save with
  "Reduce Pattern length to N or fewer." The error is correct and
  actionable, but it arrives only after the click. The manager
  fills the grid first, then learns it doesn't fit.
- **Possible direction:** Inline hint next to the cycle picker.
  When a specific week is chosen, compute the span and gray out
  cycle lengths greater than the span. Show "This pattern has N
  weeks until the next pattern" as a small caption. Client-side
  only — server-side validation stays as the authority.
- **Priority:** Low. Current error is acceptable; this is polish.

### `reset_local_db.py` PGPASSFILE

- **Origin:** FIXED-015 follow-up (which noted the scope limit) /
  FIXED-021 pattern.
- **Problem:** `restore_local_db.py` now uses a temp `PGPASSFILE`
  (0600, cleaned in `finally`) rather than the `PGPASSWORD` env
  var. `reset_local_db.py` — which `restore_local_db.py` invokes
  for the destructive drop-and-create step — may still use
  `PGPASSWORD` if it drops/creates via psql over TCP. Same threat
  model, same fix.
- **Possible direction:** Extract the passfile-building into a
  small helper both scripts use. Or copy the block if extraction
  is overkill for two call sites.
- **Priority:** Low. Dev-only script; password also in `.env` on
  the same disk, so real delta is small. Do it when the file next
  needs work.

### Notify / retroactive-confirmed survive cycle-length swap

- **Origin:** BUG-003/007 scope-limited note (FIXED-010).
- **Problem:** When the cycle-length picker triggers the HTMX swap,
  the client-side `valueCache` (FIXED-010) preserves typed time
  inputs across the swap — but not the "Notify employee" checkbox
  or the `retroactive_confirmed` hidden input. A user who ticks
  Notify, then changes cycle length, silently loses the check.
  Same for a retroactive save: confirming, then changing cycle,
  drops the confirmation (the user has to re-confirm, which is
  correct UX-wise for a destructive action — but the check isn't
  what was doing it, the cache just doesn't include it).
- **Possible direction:** Extend `valueCache` to snapshot and
  restore checkbox / hidden-input state too. Or, for
  `retroactive_confirmed`, deliberately do NOT restore it (the
  user re-confirming after a cycle change is arguably the right
  safety behavior — the semantics shifted).
- **Priority:** Low, cosmetic for Notify, arguably correct for
  retroactive-confirmed. Revisit if friction surfaces.

---

## Waiting on a specific branch

- **Write-access model — permission-first, Management layered.**
  Security sweep branch. Detail in `design/SESSIONS.md`
  ("Handed to future branches"). Move to that branch's
  `BUGREPORT.md` when the branch opens.

---

## Closed

_(Items move here after a branch ships their fix, one line each
with the shipping commit. Pruned during branch cleanup — the point
is a short historical record, not a permanent log. Git log is the
archive.)_