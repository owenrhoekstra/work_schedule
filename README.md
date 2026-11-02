# Work Schedule

A web application for managing employee work schedules. Managers build
recurring shift patterns — including multi-week rotations — set
exceptions for individual days, and manage the full lifecycle of each
employee's employment. Employees see their upcoming schedule at a
glance.

Designed for small-to-medium workplaces where schedules change week to
week and someone needs to keep track of who's working when.

---

## What it does

Work Schedule replaces the spreadsheet-and-text-message scheduling that
small workplaces usually fall back on. It centralizes shift patterns,
keeps a history of every schedule change, and gives both managers and
employees a single place to check what's coming up.

The app makes a specific set of trade-offs:

- **Patterns over per-week editing.** Most schedules repeat. Defining a
  pattern once and letting it play out avoids re-entering the same
  hours every week.
- **Overrides over pattern changes.** A one-day exception shouldn't
  require rewriting the pattern. Click a cell, change the day, move on.
- **Written history matters.** Editing a past week takes an explicit
  confirmation. Deactivating an employee doesn't erase their history.
  The schedule remembers what actually happened.
- **Quiet by default.** No email goes out without a manager ticking a
  checkbox first. Setup doesn't blast the whole team.

---

## Features

### For managers

- **Weekly schedule view** — every active employee and their shifts at
  a glance, with a date picker for jumping to any week.
- **Multi-week cycle patterns** — 1, 2, 3, or 4-week rotations (e.g.
  mornings this week, afternoons next). Cycles align across the team,
  so "Week B" means the same week for everyone on a 2-week cycle.
- **Flexible pattern editing** — change a schedule from any future week
  forward (splitting the previous pattern cleanly at the boundary), or
  edit an existing pattern in place. Retroactive edits require an extra
  confirmation.
- **Per-day overrides** — change one employee's shift for one specific
  date without touching their default pattern. Overridden cells render
  in coral so exceptions stand out.
- **Day-level statuses** — mark a whole date as Closed or Holiday and
  every employee's cell for that day is suppressed.
- **Pattern history** — every employee's full timeline of schedule
  changes, expandable week-by-week.
- **Employment lifecycle** — deactivate an employee (setting a final
  working day) and reactivate them later without losing their history.
  The schedule correctly shows gaps between periods.
- **Opt-in notifications** — welcome, approval, schedule-change, and
  deactivation emails, each triggered only by an explicit checkbox.

### For employees

- **Upcoming schedule** — a clean view of their week, with the current
  cycle position shown when the pattern rotates.
- **Email-based signup** — employees sign up with the email a manager
  recorded for them; no shared links, no invite codes to distribute.
- **Self-service profile** — update name and contact details without
  going through a manager.

### Security and access

- **Invite-only signup** — an account can only be created against an
  email that a manager has already added to the roster. Unknown emails
  are rejected at signup.
- **One-time-code verification** — signup and password changes are
  gated by a fresh email code, valid 5 minutes. Applies to both the
  normal account flow and the admin portal.
- **Rate limiting** — repeated failed logins lock out the account
  temporarily, per username + IP.
- **Approval workflow** — new accounts require a manager's approval
  before they become active, so the app never grants access to an
  unvetted signup.

---

## Design principles

These are the rules the app is built around. They explain why certain
behaviors differ from what you might expect from a generic scheduler.

### Reading is summary; writing is deliberate

A newly-added employee has no schedule until a manager creates one.
There is no auto-generated starter pattern. Adding someone to the
roster and deciding what hours they work are two separate decisions,
and the app treats them that way. The reading page surfaces three
distinct states — currently scheduled, past schedules but not this
week, or no schedule at all — so a manager always knows which case
they're looking at.

### Every edit is a boundary

Changing a schedule from a given week forward splits the existing
pattern at that boundary. The weeks before the split keep their
original hours; the weeks after use the new ones. Nobody's history
silently rewrites itself.

### Destructive actions announce themselves

Editing an already-saved pattern that starts in the past triggers a
retroactive confirmation. Deleting a pattern asks first. Deactivating
an employee opens a modal naming the last working day. Every action
that changes written history is one click harder than an action that
doesn't.

### Employment is a timeline, not a flag

An employee can be active, scheduled for future departure, or already
departed — and can move between those states without erasing what came
before. Rehires pick up where the last period ended. The schedule
always answers "was this person employed on this specific date?" not
"are they on the roster right now?"

### The manager controls the volume

Nothing is emailed to an employee without a manager checking a box.
Welcome emails, schedule changes, deactivations — all opt-in per
action. Setup doesn't produce noise. Notifications are a tool, not a
default.

### Sessions expire gracefully

If a manager's session expires while they're mid-edit, the app sends
them back to login with their work preserved in the form they return
to. Broken login pages inside half-rendered schedules aren't part of
the experience.

---

## Built on

Django on PostgreSQL, with a small HTMX + Alpine.js layer for the
interactive schedule grid. Deployed behind a Cloudflare Tunnel with
Redis for sessions and OTP storage. Full technical detail — local
setup, deployment, backups, coding conventions — lives in `docs/` and
`AGENTS.md`.

---

## License

Copyright (c) 2026 Owen R. Hoekstra. All rights reserved.

This software and its source code are proprietary and confidential.
Unauthorized copying, distribution, modification, or use of this
software, in whole or in part, is strictly prohibited without prior
written permission from the copyright holder.