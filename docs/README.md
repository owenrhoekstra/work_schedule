# Docs

Living documents for the work_schedule project.

## Structure

### Per-branch work (cleared at merge)

- `worklog/BUGREPORT.md` — active bugs on the current branch. Cleared
  at merge; surviving items go to `ISSUES.md`.
- `worklog/FIXED.md` — bugs fixed on the current branch. Cleared at
  merge; follow-up notes inside FIXED entries get extracted into
  `ISSUES.md` before clearing. Git commit log is the permanent
  archive.

### Design (persistent across branches)

- `design/SESSIONS.md` — chronological design decisions from each
  session. Grows with each branch; never cleared. The permanent
  rationale record for why the app is built the way it is.
- `design/CSP_PLAN.md` — deferred Content Security Policy branch
  plan. Phase 1 policy draft, Phase 2 nonce requirements, deployment
  caveats. Persistent until the CSP branch ships; potentially
  deleted or archived at that point (the CSP branch's own worklog
  would then hold the results).

### Queues (persistent across branches)

- `UX_BACKLOG.md` — forward-looking UX and feature requests. Items
  move to `ISSUES.md` (or directly into a branch) when they mature
  into a session.
- `ISSUES.md` — persistent queue of follow-ups awaiting a branch.
  Items move out of `ISSUES.md` and into a branch's docs when a
  branch picks them up.

### Reference (persistent; read when relevant)

- `DEPLOYMENT.md` — production deployment: server layout, first
  deploy, redeploy, rollback, services, backups, deployment caveats.
- `STAGING.md` — staging environment setup: parallel stack, isolated
  tunnel/data/access, Cloudflare Tunnel + Access config.

Reference docs aren't lifecycle-managed — they're read on demand and
updated when the infrastructure they describe changes. They live in
`docs/` so operational detail doesn't bloat the repo-root `README.md`
(product-facing) or `AGENTS.md` (code guidance).

## Why the split

Bug tracking, fix history, design rationale, feature backlog, and
operational reference serve different lifecycles:

- **Bugs** clear at merge (either fixed or became `ISSUES.md` entries).
- **Fixed** entries clear at merge (git log is the archive; flagged
  follow-ups go to `ISSUES.md`).
- **Design decisions** inform future sessions and don't expire.
- **Backlog** (UX) accumulates until an item matures into a session.
- **Issues** accumulates until a branch picks items up.
- **Reference** describes infrastructure — read when you need it,
  not part of any branch cycle.

Keeping them separate means each file stays accurate for its
lifetime instead of accumulating cruft. A fresh branch starts with
an empty BUGREPORT and an empty FIXED, but `design/`,
`UX_BACKLOG.md`, `ISSUES.md`, and the reference docs carry forward
unchanged.

## Lifecycle at merge

Before merging to main:

1. Any item left in `worklog/BUGREPORT.md` becomes an entry in
   `ISSUES.md` (or, if it belongs in a specific future branch,
   goes to that branch's plan).
2. Any known-limitation or follow-up notes flagged inside
   `worklog/FIXED.md` entries are extracted into `ISSUES.md`
   with a one-line origin breadcrumb.
3. Both `worklog/` files are emptied (headers stay, content goes).
4. `design/SESSIONS.md`, `design/CSP_PLAN.md`, `UX_BACKLOG.md`,
   `ISSUES.md`, `DEPLOYMENT.md`, and `STAGING.md` are untouched.

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
4. If the branch is CSP work, `design/CSP_PLAN.md` is the starting
   point — it carries the policy draft, Phase 2 nonce requirements,
   and deployment caveats that would otherwise need to be re-derived.

## Related docs

- `README.md` (repo root) — product overview: what the app does,
  feature set, design principles. Product-facing, not developer-facing.
- `AGENTS.md` (repo root) — AI coding agent guidance: stack,
  conventions, HTMX/Alpine sharp edges, auth gating, testing, gotchas.
- `Employee schedule page — redesign.txt` (repo root) — the
  redesign plan and top-level principles. Consider moving to
  `docs/design/` eventually; untouched for now.