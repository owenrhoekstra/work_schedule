# Docs

Living documents for the work_schedule project.

## Structure

- `worklog/BUGREPORT.md` — active bugs on the current branch. Cleared
  at merge; surviving items go to `ISSUES.md`.
- `worklog/FIXED.md` — bugs fixed on the current branch. Cleared at
  merge; follow-up notes inside FIXED entries get extracted into
  `ISSUES.md` before clearing. Git commit log is the permanent
  archive.
- `design/SESSIONS.md` — chronological design decisions from each
  session. Persistent across branches.
- `UX_BACKLOG.md` — forward-looking UX and feature requests.
  Persistent across branches; items move to `ISSUES.md` (or directly
  into a branch) when they mature.
- `ISSUES.md` — persistent queue of follow-ups awaiting a branch.
  Items move out of `ISSUES.md` and into a branch's docs when a
  branch picks them up.

## Why the split

Bug tracking, fix history, design rationale, and feature backlog
serve different lifecycles:

- **Bugs** clear at merge (either fixed or became `ISSUES.md` entries).
- **Fixed** entries clear at merge (git log is the archive; flagged
  follow-ups go to `ISSUES.md`).
- **Design decisions** inform future sessions and don't expire.
- **Backlog** (UX) accumulates until an item matures into a session.
- **Issues** accumulates until a branch picks items up.

Keeping them separate means each file stays accurate for its
lifetime instead of accumulating cruft. A fresh branch starts with
an empty BUGREPORT and an empty FIXED, but SESSIONS and UX_BACKLOG
carry forward unchanged.

## Lifecycle at merge

Before merging to main:

1. Any item left in `worklog/BUGREPORT.md` becomes an entry in
   `ISSUES.md` (or, if it belongs in a specific future branch,
   goes to that branch's plan).
2. Any known-limitation or follow-up notes flagged inside
   `worklog/FIXED.md` entries are extracted into `ISSUES.md`
   with a one-line origin breadcrumb.
3. Both `worklog/` files are emptied (headers stay, content goes).
4. `design/SESSIONS.md`, `UX_BACKLOG.md`, and `ISSUES.md` are
   untouched.

## Lifecycle at branch start

When opening a branch to tackle some of `ISSUES.md`:

1. Move the picked items **out of** `ISSUES.md` (they don't
   linger — the branch's own docs are now the tracking surface).
2. Bug-shaped items go into `worklog/BUGREPORT.md`. UX-shaped
   items go into `UX_BACKLOG.md` under "Open" until the branch
   commits to them. Design-shaped items may get a SESSIONS
   pre-entry if useful.
3. `ISSUES.md` shrinks by the number of items you picked.
   Everything that stays is still queued.

## Related docs

- `AGENTS.md` (repo root) — AI coding agent guidance: stack,
  conventions, HTMX/Alpine sharp edges, testing, gotchas.
- `Employee schedule page — redesign.txt` (repo root) — the
  redesign plan and top-level principles. Consider moving to
  `docs/design/` eventually; untouched for now.