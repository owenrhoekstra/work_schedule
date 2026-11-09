# Multi-tenancy — branch record

## Status

**IN DESIGN (branch start 2026-11-09).** Branch 0 plan-complete;
Branches 1–2 outlined (need file reads to finalize); branches 3+
follow the per-feature dual-endpoint pattern. Nothing built yet.

**This file is the branch record and the durable plan.** Unlike
`worklog/BUGREPORT.md` and `worklog/FIXED.md` — cleared at merge —
it persists past the branch's merge because it holds the design
rationale and model decisions the whole multi-tenancy effort depends
on. `SECURITY_SWEEP.md` is a peer permanent record and stays where it
is; neither file supersedes the other.

## Why this branch exists

`AGENTS.md` calls the app "currently scoped to a single workplace"
with a stated multi-tenancy / SaaS direction, "deliberately structured
so those are additive rather than rewrites." This branch makes that
real:

- `Company` and `Team` models land; every domain root gains a
  `company` FK; authz moves from "one global `Management` group" to
  "membership-derived company/team admins."
- A session-scoped `request.company` (and optional `request.team`)
  replaces the implicit single-tenant assumption.
- The app becomes `docket` eventually; nothing here renames
  user-facing strings, but every decision survives the rename.
- **In parallel**: HTML → Vue SPA, Django views → Django Ninja API →
  eventually a hand-rolled Go backend. Every feature branch in this
  effort ships **both** an HTML endpoint and an `/api/v1/` endpoint,
  so the SPA can be wired page by page and the Go swap is a
  replacement, not a rewrite.

Scope discipline: **good not perfect.** Ship companies + teams +
memberships + per-company authz + Ninja foundation. Defer Postgres
RLS, OIDC, self-serve onboarding, and Go — documented below so they
are picked up from a known state.

## Decisions log

### Foundational

- **This instance becomes the multi-tenant SaaS.** One codebase, one
  deployment, many companies. The rename to `docket` is branding, not
  a codebase split.
- **No tenant subdomains.** Everything lives at fixed subdomains of
  `principiasystems.ca`; tenants do not bring domains. Tenant
  resolution is session-based. Rejected: subdomain-per-tenant,
  URL-prefix per tenant.
- **Cloudflare Access gates staging only.** Prod is open; Django owns
  auth. Staging keeps its one-time-PIN Access policy.
- **Global users, split membership model.** `User` is the source of
  truth for identity and authn. OIDC (Zitadel or Keycloak)
  eventually owns authn — the schema must make attaching an OIDC
  identity a config change, not a schema change.

### Model shape

- **`Employee` is scheduling-only and split from
  `CompanyMembership`.** Split model, not merged. `Employee` holds
  start date, last day, patterns, overrides. `CompanyMembership`
  says "this user can access this company." An admin can be a
  member without being an employee; an employee can exist without a
  user (manager creates employee, person signs up afterward).
- **`Employee.user` is nullable and becomes `ForeignKey`** (was
  `OneToOneField`). `UniqueConstraint(user, company)` where not
  null. Makes "employee before user" work and allows one user to be
  an employee at multiple companies (one Employee per company).
- **`TeamMembership` (authz) and `EmployeeTeam` (scheduling) are
  both through tables, both carry history.** `TeamMembership`:
  user↔team, role, valid_from/valid_to. `EmployeeTeam`:
  employee↔team, is_default, valid_from/valid_to. They can diverge
  — a team admin may not be a schedulable employee; an employee may
  have no user yet. History matters for audit from day one,
  mirroring the `effective_to`-exclusive discipline on
  `ShiftPattern`.
- **`Company` FK on domain roots only, derive on children.**
  Direct FK on: `Employee`, `EmploymentPeriod`, `ShiftPattern`,
  `DayOverride`, `Role`, `Title`. Derive via parent on `Shift`,
  `ShiftOverride`. Rejected: FK on every model (drift risk). Joins
  are cheap; can add later if profiling demands.
- **`UniqueConstraint(id, company)` on each root** so composite FKs
  on children are available later.
- **`DayOverride.team` is a nullable FK.** Null = company-wide
  (stat holiday, closure); set = team-only (kitchen deep-clean). A
  company-wide override applies to every team; a team override
  applies only to that team.
- **`ShiftOverride` stays per-employee** (one employee's shift on
  one date; no team scoping).
- **`Role` and `Title` are company-scoped with a nullable team FK.**
  Preset defaults are code constants seeded into company-wide rows
  at company creation. Company edits fork from preset. Teams can
  optionally fork their own (independent once forked).
- **UUIDv7 PKs via DB-side `uuidv7()` (PG 18).**
  `UUIDField(primary_key=True, db_default=Func(...))`. Fallback:
  `default=uuid.uuid7` (Python 3.14 stdlib).

### Authz

- **Explicit decorators, not a redefined `management_required`.**
  `management_required` is retired. Replacements:
  - `company_admin_required` — active company admin at
    `request.company`.
  - `team_admin_required` — active team admin at `request.team`
    (implies active company membership).
  - `any_admin_required` — company admin OR team admin in current
    context. Workhorse for most write views.
  - `platform_admin_required` — Django `is_staff`. `/admin/`,
    Ninja docs, Axes admin.
  - `employee_required` — has an `Employee` record at
    `request.company`.

  Every decorator reads `request.company` (`request.team` where
  relevant). `is_staff` does not imply company admin.

- **Two-layer model survives.** Django perms (`schedule.change_shift`
  etc.) stay as coarse capability gates; membership-derived admin
  status is the second layer. Every write view is
  `@permission_required("schedule.X") @<admin>_required` — outer
  admin check, then capability, then body. Same shape as today; only
  the second layer's source changes.
- **`Management` group is retired as the authz mechanism.**
  Existing members migrate to `CompanyMembership(role="admin",
status="active")` at the seed company. Recommended: rename the
  group to `Platform Admin` and keep it holding Django
  `schedule.*` perms; stop referencing it in decorators. Delete
  the group only if per-user perms are granted directly.
- **Per-company / per-team admin from memberships, not groups.**
  `CompanyMembership.role ∈ {"admin", "member"}`. `TeamMembership`
  carries the same role set. Company admin sees all teams; team
  admin sees only granted teams (grant made by a company admin).
- **Team admin exists even though company admin implies every team
  admin power.** Kept for explicit UI assignment (someone responsible
  for a team); code path is uniform via `any_admin_required`.
- **`management_required` → `company_admin_required`** on every
  existing view it gates (all company-level: settings, deactivate,
  reactivate, add employee). Mechanical rename.
- **`EmployeeDeactivationMiddleware` becomes per-company.** A user
  deactivated at Company A can still reach Company B if active
  there. It checks the current session company's employment state
  only. Global session invalidation is out of scope.

### Tenancy mechanics

- **Session-based, not URL-based.** `request.session["company_id"]`
  (and optional `["team_id"]`) set at login. `TenantMiddleware`
  reads them into `request.company` / `request.team` on every
  request. Views, selectors, and templates read from
  `request.company`, never from URL segments. No `/c/<uuid>/`
  prefix.
- **Login picker** when user belongs to >1 company. Single-company
  members skip it. Picker excludes
  `CompanyMembership(status="pending")` rows — pending memberships
  surface via an acceptance page instead.
- **Email links and QR codes carry `?company=<uuid>`.** The one
  place company ID appears in a URL; only on acceptance/invite
  flows. Once the session is set, the param is ignored.
- **Application-level filtering, not Postgres RLS (v1).** Every
  selector takes `company` (and `team` where relevant) as its first
  argument. RLS is a later hardening layer; the schema and
  selectors are shaped so enabling it is additive.
- **Session stores company and team.** `["company_id"]` required
  for any tenanted request; `["team_id"]` optional, set only with a
  specific team context. Company admins with "all teams" have
  `["team_id"]` absent.

### Team behavior

- **`Team.allow_member_view_all`** (team-level boolean). When true,
  every team member can toggle their home view to see the whole
  team's schedule. When false (default), members see only their
  own. Company admins always see all; team admins always see their
  team. Set by a team admin or company admin.
- **`Employee.show_team_schedules`** (per-employee boolean). Only
  relevant when `team.allow_member_view_all=True`. If off, that
  employee's home view falls back to their own schedule. Affects
  only that employee.
- **Multi-team employees see stacked schedules.** Each team's
  schedule as a labeled block ("Kitchen", "Front House").
  Merged-and-labeled-by-shift is a future frontend toggle; backend
  serves both shapes trivially.
- **Team admin can be admin of multiple teams** (across companies
  too). Schema supports it: global user, per-company memberships,
  per-team `TeamMembership` rows.

### Roles / titles semantics

- **Preset defaults are code constants, not DB rows.** Seeded into
  company-wide `Role`/`Title` rows at company creation. Teams can
  optionally fork company-wide defaults into team-scoped rows.
- **Company can edit its company-wide default.** Editing mutates
  the company's row (forking from preset). Non-forked teams
  inherit; forked teams are unaffected.
- **Teams can fork.** Team-scoped rows are independent once created.
  Matches "scoped once changed."
- **No cross-tenant relationship.** Presets are the only shared
  naming reference.

### API foundation (Ninja)

- **`/api/v1/` namespace, per-app routers.** `work_schedule/api/`
  for shared plumbing; `schedule/api.py` and `accounts/api.py` for
  per-app routers. Version locked at v1 until API-only ships.
- **Session auth only for v1.** Reuses the Django session cookie;
  CSRF via `X-CSRFToken` header (matches HTMX). Token auth is a
  later branch timed with Go.
- **Pydantic v2 response schemas on every endpoint.**
  `/api/v1/docs` gated to `platform_admin_required`. Same-origin
  SPA; no CORS.
- **HTML views and API views call shared services and selectors.**
  Business logic lives in `schedule/services.py` (writes) and
  `schedule/selectors.py` (reads), called by both. Rejected: HTML
  views calling the API over HTTP (overhead with no benefit before
  the Go split). Helper signatures can churn; JSON contract is
  stable.
- **Every new feature ships HTML + API in the same branch.**
  HTML-only is not permitted going forward; API-only is fine when
  the feature has no HTML surface.
- **SPA serves from the same origin.** Vue fetches `/api/v1/...`
  with the session cookie. Feature branches that dual-serve a
  feature can wire the Vue page at the same time.

### Branch plan

Branches ship green at every step.

#### Branch 0: `ninja-foundation`

**Ships:** Django Ninja installed, `/api/v1/` mounted, session
auth, permission-class stubs, docs gated, one smoke endpoint,
`AGENTS.md` additions.

**Does not ship:** any model, template, or migration change.

**Dependencies:** none. Can start immediately.

#### Branch 1: `mt-1-models`

**Ships:** `Company`, `Team`, `CompanyMembership`, `TeamMembership`,
`EmployeeTeam`. `Employee.company` FK; `Employee.user`
`OneToOne`→`ForeignKey` + `UniqueConstraint(user, company)`.
`company` FK on `EmploymentPeriod`, `ShiftPattern`, `DayOverride`,
`Role`, `Title`. `Team.allow_member_view_all`.
`Employee.show_team_schedules`. `DayOverride.team` nullable FK.
UUIDv7 PKs. Backfill command. Factories updated; every existing
test class gets a company.

**Does not ship:** any behavior change. `request.company` is not
wired; every existing query implicitly assumes one company.

**Dependencies:** file reads of `schedule/models.py`,
`schedule/tests/factories.py`, `work_schedule/settings.py`.

**Migration strategy:**

1. Migration A: add new models; add nullable `company` FKs;
   alter `Employee.user` to `ForeignKey` (still nullable, no
   uniqueness change yet).
2. Management command `bootstrap_company --name … --slug …`:
   creates seed `Company`; backfills `company_id` on every row;
   converts every `Management`-group member to
   `CompanyMembership(role="admin", status="active")`;
   optionally creates teams from a comma-separated list.
3. Migration B: tighten `company` FKs to non-nullable; add
   `UniqueConstraint(company, name)` on `Team`; add partial
   `UniqueConstraint(user, company)` on `Employee`.
4. Post-migration: rename `Management` → `Platform Admin`
   (recommended) or delete. Group stops being referenced in
   decorators after Branch 2 either way.

Seed company name/slug come from CLI args, not env vars — migration
is a no-op on a fresh DB with no command run. On a populated DB,
the command is required before Migration B.

#### Branch 2: `mt-2-plumbing`

**Ships:** `TenantMiddleware` (reads session → `request.company` /
`request.team`). Login picker. Context processors (`app_name`,
`is_company_admin`, `is_team_admin`) reading from
`request.company`. `management_required` removed; every gated view
moves to `company_admin_required` (or `any_admin_required`).
`EmployeeDeactivationMiddleware` scoped per company. Email sender
takes `company=`; `send_email` signature changes. QR builds from
`company.site_url`. Login consent flow
(`CompanyMembership(status="pending")` + acceptance page). Stacked-
schedule UI for multi-team employees (template-level).

**Does not ship:** the home dual-endpoint (Branch 3).

**Dependencies:** Branch 1 complete; file reads of
`work_schedule/middleware.py`, `work_schedule/context_processors.py`,
`accounts/views.py`, `schedule/notifications.py`.

**Testing strategy:** helper `login_as(client, user, company,
team=None)` — `force_login` + session set. Every test class
migrates to it. Factories gain `make_company_admin_user(company)`
(mirrors today's `make_management_user()`).

#### Branch 3: `mt-3-home-dual`

**Ships:** first dual-served feature.

- `GET /` (HTML home) — selectors filtered by `request.company`
  (+ `request.team`), gated on `employee_required` OR
  `any_admin_required`.
- `GET /api/v1/home/` — same data, Pydantic-serialized, same
  gating.
- `schedule/selectors.py::schedule_for_week(company, team,
week_start, viewer)` shared by HTML and API.
- Vue SPA home wired against `/api/v1/home/`, replacing
  `home.html` for opted-in users.

**Dependencies:** Branch 0, 1, 2 complete.

#### Branch N (3+): `mt-N-<feature>`

**Pattern per branch:** one feature, dual-served.

- Read-side: extract selector; wire HTML view; wire API endpoint.
- Write-side: extract service; wire HTML form POST; wire API POST.
- Same decorators/permission classes on both.
- Tests: existing HTML tests stay; add `ninja.testing.TestClient`
  cases mirroring them.
- If email is sent: pass `request.company` to `send_email`.

**Suggested order:**

1. `set_override` — write path; establishes the write-service
   pattern.
2. `pattern_form` — most complex feature; dual-serve after the
   write pattern is settled.
3. `settings_*` — company config; also where `Role`/`Title`
   team-forking lands.
4. `print` / `qr` — read paths, minor.
5. `details` — identity edit + deactivation.
6. `team admin` UX — team picker, grant-teams, per-team day-
   override resolution (column exists from Branch 1).

#### Deferred

- **Self-serve onboarding** — decide at end of branch. Company
  creation self-serve; employee TOTP signup (72h single-use codes;
  manager approval still required).
- **OIDC (Zitadel/Keycloak)** — separate branch. Schema shaped so
  adding an OIDC backend is a setting + new auth backend, not a
  model change.
- **Postgres RLS** — separate branch. Selectors already scoped;
  enabling is `SET LOCAL app.current_company` per request + per-
  table policies + pooling audit.
- **Go backend** — replaces Django once SPA is fully Vue. JSON
  contract matters; helper signatures can churn.
- **Multi-team merged-view toggle** — frontend only.

### Cross-cutting concerns

#### Role / Title forks

| Layer           | Source                  | Editable by         | Auto-updates?                 |
| --------------- | ----------------------- | ------------------- | ----------------------------- |
| Preset          | code constant           | platform maintainer | yes (redeploy)                |
| Company default | row with `team_id=NULL` | company admin       | not from preset after fork    |
| Team fork       | row with `team_id` set  | team admin          | no (independent once created) |

- Deleting a company default with team forks is rejected until
  forks are resolved (mirror "earliest-pattern guard": hidden UI
  is not a permission).

#### Middleware ordering

`TenantMiddleware` runs on the request phase and must sit above
both `HTMXLoginRedirectMiddleware` and
`EmployeeDeactivationMiddleware` — the deactivation middleware now
reads `request.company`, and the HTMX-302 rewrite still needs to
wrap the deactivation 302 (Session 10 load-bearing ordering).
... Django defaults ...
work_schedule.middleware.TenantMiddleware (new)
work_schedule.middleware.HTMXLoginRedirectMiddleware
work_schedule.middleware.EmployeeDeactivationMiddleware
... rest ...

#### Login picker / consent flow

| Case                                                         | Behavior                                                                                                                     |
| ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------- |
| New email, no `User`                                         | Employee created (no link); invite email; signup creates User; manager approval activates `CompanyMembership`                |
| Existing active `User`, manager adds                         | Employee created + linked; `CompanyMembership(status="pending")`; consent email with `?company=<uuid>`; acceptance activates |
| Existing deactivated `User`, manager adds                    | Same; acceptance also reactivates `User`; no picker — straight into the inviting company                                     |
| Existing deactivated `User`, self-serve reactivation (later) | Routes through picker; **does not auto-rejoin** the company they were deactivated from                                       |

Pending memberships excluded from the login picker. Acceptance
page reads `?company=<uuid>`, presents yes/no, sets
`status="active"`, logs the user in.

#### Migration from `Management` group

`bootstrap_company`:

1. Create seed `Company`.
2. For each `Management` member, create
   `CompanyMembership(role="admin", status="active")` at seed.
3. Rename the group to `Platform Admin` (recommended), keeping its
   `schedule.*` perms; stop referencing it in decorators. Or
   delete once references are gone.
4. Grant migrated admins their `schedule.*` perms — either
   directly on `User` or by keeping the renamed group as perm
   holder. Recommended: keep the group, stop using it in view
   decorators, read company admin from `CompanyMembership.role`.

#### Testing conventions

- `login_as(client, user, company, team=None)` — force_login +
  session set. Shared helper module
  (`schedule/tests/_helpers.py`).
- `make_company_admin_user(company, **kwargs)` — user +
  `CompanyMembership(role="admin", status="active")` +
  `schedule.*` perms.
- `make_team_admin_user(team, **kwargs)` — user +
  `TeamMembership(role="admin")` + active `CompanyMembership` at
  `team.company`.
- `make_employee(company=..., team=..., with_pattern=..., user=...)`
  — `company` defaults to a fresh `CompanyFactory.create()`;
  `team` defaults to no membership; `user` defaults to none.
  Existing calls keep working; shared-company tests pass
  `company=` explicitly.
- `@override_settings(CACHES=_LOCMEM_CACHES)` still required on
  every template-touching test.
- `bootstrap_company` never runs in tests — seed company is a
  production concern.

#### API conventions (added to `AGENTS.md` in Branch 0)

- `/api/v1/` namespace; per-app routers; `version="1"`.
- Session auth; CSRF via `X-CSRFToken`.
- Pydantic v2 `Schema` per app in `schemas.py`; every endpoint
  declares `response=Schema`.
- Permission classes named same as decorators (`CompanyAdmin`,
  `TeamAdmin`, `AnyAdmin`, `PlatformAdmin`, `EmployeeRequired`,
  `HasPerm("schedule.X")`).
- `/api/v1/docs` gated to `platform_admin_required`.
- Every feature ships HTML + API; shared logic in
  `services.py` / `selectors.py`. Selectors take `company` (and
  `team` where relevant) as first arg.
- `ninja.testing.TestClient` for API tests; `self.client` for HTML;
  same factories; no separate API-only factories.

## Branch 0 plan (detailed)

Concrete worklist for `ninja-foundation`. No model changes; no
migrations; no template changes.

### Dependencies

- `django-ninja` pinned in `pyproject.toml`; `uv lock` clean.
- No file reads required to start.

### File layout

work_schedule/
api/
init.py
api.py # NinjaAPI(version="1", title="Docket API")
auth.py # session auth class (thin)
permissions.py # BasePermission subclasses (stubs this branch)
urls.py # /api/v1/ include
schedule/
api.py # router — smoke endpoint only this branch
accounts/
api.py # router — smoke endpoint only this branch

### Steps

1. Install `django-ninja`; `uv lock`; confirm in venv.
2. Mount `NinjaAPI` (`work_schedule/api/api.py`) with
   `docs_url="/docs"`, `openapi_url="/openapi.json"`. Register
   routers under `/api/v1/`.
3. Session auth class in `work_schedule/api/auth.py` — thin
   `SessionAuth` subclass; document that `CsrfViewMiddleware` +
   `X-CSRFToken` header is the CSRF contract.
4. Permission class stubs in `work_schedule/api/permissions.py`.
   `PlatformAdmin` implements `is_staff`; `CompanyAdmin`,
   `TeamAdmin`, `AnyAdmin` are placeholders returning True until
   Branch 2 wires `request.company`.
5. Smoke endpoint `GET /api/v1/smoke/me/` — returns user id,
   email, `is_staff`. Mount a single router from
   `work_schedule/api/smoke.py` to avoid duplicate endpoints.
6. Gate `/api/v1/docs` and `/api/v1/openapi.json` to
   `platform_admin_required` by overriding
   `NinjaAPI.get_openapi_schema` to raise 403 for non-staff
   (covers both routes).
7. `AGENTS.md`: add "API conventions (Django Ninja)" section.
8. `docs/README.md`: add `docs/MULTI-TENANCY.md` under
   per-branch work.
9. Tests (`schedule/tests/test_api_smoke.py`):
   - `test_me_returns_current_user` — authenticated via
     `ninja.testing.TestClient`.
   - `test_me_requires_auth` — anonymous → 401.
   - `test_docs_requires_staff` — anonymous 401; non-staff 403;
     staff 200.
   - `test_openapi_json_requires_staff`.
   - `test_api_url_prefix` — `/api/v1/` resolves; `/api/` 404s.
10. Pre-commit: `collectstatic --noinput && check && test &&
uv lock --check`.

### Explicit non-goals

- No model changes, template changes, migrations.
- No auth/perm behavior changes (`is_staff` still gates admin;
  `Management` still gates company views).
- No `request.company` wiring.
- No API endpoints beyond the smoke + docs.
- No `AGENTS.md` changes beyond the new API section.

### Verification before merge

- Existing suite passes unchanged.
- Smoke endpoint responds correctly for session user; 401 for
  anonymous.
- `/api/v1/docs` 200 for staff, 403 otherwise.
- `check --deploy` clean.

## Branch 1 plan (outline — finalize after file reads)

**Needs reads:** `schedule/models.py`, `schedule/tests/factories.py`,
`work_schedule/settings.py`, `work_schedule/urls.py`.

**Skeleton:**

1. `schedule/models.py`: new models per "Model shape"; alter
   existing models; `UUIDField` PKs with `db_default`.
2. Migrations A / B as described; `bootstrap_company` management
   command.
3. `schedule/tests/factories.py`: `CompanyFactory`, `TeamFactory`,
   `CompanyMembershipFactory`, `TeamMembershipFactory`,
   `EmployeeTeamFactory`; update `make_employee`,
   `make_manager_user`, `make_management_user` to accept
   `company=`.
4. Bulk test update: every `make_employee(...)` and
   `make_*_user(...)` call gets a company (explicit or default).
5. `AGENTS.md`: new models in "Key models"; factory conventions;
   note the `make_employee` company default.
6. `docs/design/SESSIONS.md`: "Session 11 — Multi-tenancy models"
   recording split-vs-merged, FK strategy, UUIDv7 choice.

## Branch 2 plan (outline — finalize after file reads)

**Needs reads:** `work_schedule/middleware.py`,
`work_schedule/context_processors.py`, `accounts/views.py`,
`schedule/notifications.py`, `schedule/views.py` (section banners

- read paths).

**Skeleton:**

1. `TenantMiddleware` — reads session; sets `request.company` /
   `request.team`; 400 if authed without company.
2. `EmployeeDeactivationMiddleware` — scope per company.
3. Context processors — read from `request.company`; expose
   `is_company_admin`, `is_team_admin`.
4. Decorators — replace `management_required` with
   `company_admin_required`, `team_admin_required`,
   `any_admin_required`, `platform_admin_required`,
   `employee_required`.
5. `accounts/views.py` — login picker, consent flow, session setup
   after login.
6. `schedule/notifications.py` — `send_email(company, ...)`;
   update every caller.
7. `schedule/views.py` — decorator swap on every formerly-
   `management_required` view.
8. Templates — `{% if is_management %}` →
   `{% if is_company_admin %}` (or `is_team_admin` where
   relevant).
9. Tests — bulk migration to `login_as` helper and
   `make_company_admin_user`; every test gets a company in the
   session.
10. `AGENTS.md` — middleware ordering note; updated key models;
    updated decorator section; rewritten factory section.
11. `docs/design/SESSIONS.md`: "Session 12 — Multi-tenancy
    plumbing" recording middleware ordering and decorator
    replacement.

## Open questions / deferred decisions

Not blockers for Branch 0; resolve during Branches 1–2 as code
dictates.

- **`Management` group retention** — rename to `Platform Admin`
  and keep as perm holder (recommended), or delete entirely once
  decorators are replaced. Branch 2 decides.
- **Per-company Role/Title preset list** — code constant in
  `schedule/constants.py`. Start minimal (e.g., `["Manager",
"Supervisor", "Cashier", "Cook"]`); grow from feedback.
- **`EmployeeTeam.is_default` invariant** — recommend "at most
  one" via partial unique constraint + `first()` fallback, rather
  than "exactly one." Branch 1 decides.
- **Team picker for team admins** — skip when admin of one team;
  always show for company admin. Decide in Branch 2 or team-admin
  branch.
- **Consent link TTL** — recommend 7 days (TOTP is 72h; consent
  is less urgent but still bounded). Settings constant.
- **Vue page swap strategy** — feature flag per user, per route,
  or per company. Branch 3 decides.
- **`request.team` when company admin hasn't picked a team** —
  `None` = all-teams view; views needing a specific team check
  `request.team is not None`.

## Lifecycle at merge

- **Branch 0**: no worklog content (no bugs, no fixes). No
  extraction.
- **Branch 1**: schema rationale → `docs/design/SESSIONS.md` as
  "Session 11 — Multi-tenancy models."
- **Branch 2**: middleware ordering, decorator replacement, login
  picker decisions → `SESSIONS.md` "Session 12 — Multi-tenancy
  plumbing."
- **Branches 3+**: per-feature rationale → `SESSIONS.md` as
  "Session 13 — <feature>" etc.
- **This file (`MULTI-TENANCY.md`)** — after `mt-3-home-dual`
  ships, either delete it (decisions live in `SESSIONS.md` and
  code) or move the schema section and future-branch list into a
  persistent `docs/design/MULTI_TENANCY.md` (analogous to
  `CSP_PLAN.md`). Recommended: move to `design/` for new
  contributors and the Go rewrite team.
- **`SECURITY_SWEEP.md`** — stays where it is; peer permanent
  record, not superseded by this file.
