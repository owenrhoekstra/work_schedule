# AGENTS.md

Guidance for AI coding agents (Claude Code, Cursor, Codex, etc.) working
in this repo. Read this before making changes. If something here
contradicts what you're about to do, flag it and ask.

## Project overview

A Django web app for managing employee work schedules at a single
workplace. Managers add employees, define recurring shift patterns
(including multi-week rotations), and set per-day overrides. Employees
view the schedule and can sign up with an invite link.

Current scope: single workplace. Long-term roadmap includes multi-tenancy
(companies and teams) and SaaS licensing; the codebase is deliberately
structured so those are additive rather than rewrites. Don't build either
yet, but don't design in ways that block them.

## Stack

- **Django 6.1.1**, Python 3.14
- **PostgreSQL** for persistence, **Redis** for cache
- **Tailwind CSS** via `django-tailwind` (the `theme` app)
- **HTMX 2.x** and **Alpine.js 3.x**, vendored under `static/js/`
  (never CDN)
- **WhiteNoise** with `CompressedManifestStaticFilesStorage` for static
  assets
- **django-axes** for login rate limiting
- **Resend** via `anymail` for transactional email
- **`uv`** for dependency management (not pip, not poetry)

## Commands

All commands assume `uv run` prefix unless noted.

    uv run python manage.py runserver          # dev server
    uv run python manage.py test               # full suite
    uv run python manage.py test schedule.tests.test_home  # one module
    uv run python manage.py check              # fast syntax/config check
    uv run python manage.py collectstatic --noinput
    uv run python manage.py migrate
    uv run python manage.py shell
    uv lock --check                            # verify lockfile

**Before every commit**, run the full pre-commit sequence:

    uv run python manage.py collectstatic --noinput && \
    uv run python manage.py check && \
    uv run python manage.py test && \
    uv lock --check

`collectstatic` matters more than it looks. Static storage is
manifest-based; a template referencing a `{% static %}` file that isn't
in `staticfiles.json` raises `Missing staticfiles manifest entry` at
render time and takes every page down. Whenever you add or rename a
static file, run `collectstatic` before running tests.

## Architecture

    work_schedule/       # project settings, urls, wsgi, context processors
    accounts/            # auth, signup, OTP, profile
    schedule/            # employees, patterns, shifts, schedule view
    theme/               # Tailwind config and compiled CSS
    templates/           # project-level templates (base.html, emails, partials)
    static/              # source static files
    staticfiles/         # collectstatic output, do not edit
    docs/                # living docs (see "Docs" section below)
    scripts/             # one-off dev scripts (db reset/restore)

### Docs (living documents)

See `docs/README.md` for the full model. Short version:

- `docs/worklog/BUGREPORT.md` — active bugs on the current branch.
  Cleared at merge; survivors go to `ISSUES.md`.
- `docs/worklog/FIXED.md` — bugs fixed on the current branch.
  Cleared at merge; follow-ups extracted to `ISSUES.md`.
- `docs/design/SESSIONS.md` — chronological design rationale.
  Persistent across branches.
- `docs/UX_BACKLOG.md` — forward-looking UX/feature requests.
  Persistent.
- `docs/ISSUES.md` — persistent queue of follow-ups awaiting a branch.
  Items move out of here and into a branch's worklog when picked up.

Don't put design rationale into `FIXED.md` — it goes in `SESSIONS.md`.
Don't put active bugs into `ISSUES.md` — they go in `BUGREPORT.md`.

### Key models (`schedule/models.py`)

- `Employee` — title, name, role FK, email, optional User link,
  `start_date`, `last_day`, `is_active`
- `EmploymentPeriod` — one continuous stretch of employment per
  employee. `end_date` is **exclusive** (first day NOT employed).
- `ShiftPattern` — a snapshot of an employee's default schedule for a
  half-open range `[effective_from, effective_to)`, both Monday-aligned.
  `effective_to` is exclusive; `None` means open-ended. Holds
  `cycle_weeks` (1–4) and its `Shift` rows keyed by
  `(week_offset, day)`.
- `Shift` — one cell of a pattern: `(pattern, week_offset, day)` →
  start/end. Missing combinations mean OFF.
- `ShiftOverride` — per-employee per-date override, `is_off` flag or
  substitute times.
- `DayOverride` — whole-date status (Closed, Holiday) affecting every
  employee.

**Employee creation does not auto-create a ShiftPattern.** New hires
have no schedule until a manager sets one up. See "Pattern form domain"
below.

### Template layout

    templates/                          # project-level
      base.html                         # global shell, htmx+alpine wiring
      partials/
        _messages.html
      emails/                           # transactional emails (HTML + txt)

    schedule/templates/schedule/        # schedule app pages and pieces
      home.html
      employee_defaults.html            # reading page (read-only)
      employee_details.html             # identity + deactivation edit page
      pattern_form.html                 # change / add / edit pattern
      settings.html
      print_schedule.html               # standalone, no base.html
      partials/                         # composed into pages
        _page_header.html               # home week nav + actions
        _page_state.html                # schedulePage Alpine component (home)
        _schedule_table.html
        _schedule_row.html
        _employee_header.html
        _identity_form.html             # included on details page
        _saved_patterns.html            # pattern history on reading page
        _pattern_form_body.html         # banner + grid + footer + submit JS
      modals/                           # <dialog> elements
        _override.html, _day.html,
        _add_employee.html, _add_employee_form.html,
        _print.html, _deactivate.html,
        _delete_pattern_confirm.html,
        _retroactive_confirm.html,
        _confirm_discard.html,
        _confirm_save_pattern.html,
        _confirm_save_details.html,
        _cancel_deactivation_confirm.html,
        _week_picker.html
      icons/
        _printer.html

Pages orchestrate includes. Partials are composed into pages. Modals
are self-contained and either included from a page or conditionally
included (e.g. `_retroactive_confirm.html` only appears when the target
week is in the past).

## Code conventions

### Python

- **Python 3.14 syntax only.** `except A, B:` is invalid — always
  `except (A, B):`. This has bitten us; double-check except clauses.
- No custom user model. `Employee` links to Django's `User` via
  `OneToOneField(null=True)`. Employee is the source of truth for name
  and email; a `post_save` signal mirrors to User.
- Timezone: `America/Toronto`, `USE_TZ = True`. Use
  `timezone.localdate()` and `timezone.now()`, not `date.today()` or
  `datetime.now()`. Tests use `timezone.localdate()` for the same reason
  — a `date.today()` in a test can flake at midnight when the server's
  system timezone differs from `TIME_ZONE`.
- Test suite is `unittest`-style `TestCase`, not pytest. Factories live
  in `schedule/tests/factories.py`.
- `schedule/views.py` is large and sectioned by comment banners. Add new
  helpers to the right section rather than appending at the bottom.

### Settings you'll reach for

- `settings.SITE_URL` — absolute base URL for building links in emails
  and the QR code. Derived from env.
- `settings.APP_NAME` — branded app name. Context processor exposes it
  as `{{ app_name }}` in every template. Set via `APP_NAME` env var.
- `settings.CYCLE_EPOCH` — anchor Monday for computing which week of a
  multi-week cycle a given date falls on. The cycle-offset arithmetic
  (`_cycle_offset`, `_week_offset_for`) is anchored to this date.

### Django templates

- `{# ... #}` is **single-line only**. It does not span newlines; a
  multi-line comment with `{# ... #}` renders literally. Use
  `{% comment %} ... {% endcomment %}` for anything multi-line.
- Server-rendered values in form fields matter. See HTMX/Alpine section
  below before touching any form.

### Factories (`schedule/tests/factories.py`)

- **`make_employee()` defaults to `with_pattern=False`.** Post-Session 8,
  Employee creation does not auto-create a ShiftPattern — matching the
  app. Tests that need a pattern opt in explicitly:
  - `make_employee(with_pattern=True)` — one open-ended pattern anchored
    to the Monday of `start_date`.
  - `make_employee(cycle_weeks=N)` — implies `with_pattern=True`. Passing
    `cycle_weeks=1` explicitly *does* create a pattern; only omitting the
    arg entirely gives you no pattern.
  - This is the #1 surprise for new agents writing tests. If your test
    touches `employee.patterns` or expects a schedule to render, it needs
    `with_pattern=True` or `cycle_weeks=N`.
- `make_manager_user()` grants every schedule permission but is **not**
  a superuser and is **not** in the "Management" group. Views gated on
  `management_required` (details page, settings, print) need the user
  to be added to a Management group — see `_manager()` helpers in
  `test_details.py` and `test_settings.py` for the pattern.
- The factory uses `date.today()` for `start_date` default (minor
  deviation from the timezone rule; fine in practice because most tests
  override `start_date` explicitly).

## Pattern form domain

`pattern_form.html` + `_pattern_form_body.html` + `_week_picker.html`
form the change/add/edit surface. It's the most complex area of the
codebase — read this before touching it.

### Semantics

- A pattern covers `[effective_from, effective_to)`. Both are Monday
  dates. `effective_to = None` means open-ended.
- The form's "panel" index (`week_0`, `week_1`, ...) is a **calendar-week
  index relative to `effective_from`**, not the target pattern's cycle
  offset. Panel `i` = calendar week `effective_from + 7*i`.
- Save translates `(cal_offset, day)` → `(target_offset, day)` via
  `(base_target_offset + cal_offset) % cycle_weeks`. This is what makes
  edits land on the week the manager was looking at even when
  `effective_from` isn't congruent with `CYCLE_EPOCH`.

### Save behavior

- Split vs edit-in-place vs new is decided entirely by the submitted
  `effective_from` and which pattern covers that week. There is no mode
  flag.
- A target-span check rejects `cycle_weeks > span_weeks` before any
  writes — span is `effective_to - effective_from` for split/edit-in-
  place, or `next_pattern.effective_from - effective_from` for new.
  This prevents writing offsets the pattern will never display.
  **Exception:** the edit-in-place handler allows unchanged or reduced
  cycles on a truncated pattern (`cycle_weeks > span_weeks AND
  cycle_weeks > pattern.cycle_weeks`). Change/add has no such exception.
- Cycles-shrinking deletes orphan offsets (`week_offset >= cycle_weeks`)
  on save. Growth leaves them alone.

### Validation and value preservation

- Grid validation collects ALL errors before re-rendering, and stashes
  every successfully-parsed cell in `submitted_shifts`
  (`SimpleNamespace(start_time, end_time)` keyed by `(cal_offset, day)`).
  The error re-render uses those values instead of covering-pattern
  prefill. Parse-failed or half-parsed cells are dropped — no clean way
  to render them for the `|time` filter.
- The client-side `valueCache` in `_pattern_form_body.html`'s script
  snapshots visible time input values on `htmx:beforeRequest` (cycle
  picker), restores them from `htmx:afterSwap`. Persists across
  shrink-then-grow. Cleared on submit and on week change.
- Hidden-week POST cells (`cal_offset >= cycle_weeks`) are skipped in
  both parse and save loops. Without this, a stale `week_2` cell from a
  cycle-shrink swap would modulo-map back onto a visible offset and
  overwrite it.

### Confirmations

- Every save routes through a confirmation modal.
- Non-retroactive: `_confirm_save_pattern.html`.
- Retroactive: `_retroactive_confirm.html` (dual-duty — it *is* the
  warning AND the save confirmation, one click).
- Cancel routes through `_confirm_discard.html` (unsaved-changes
  warning).
- Wiring: `_pattern_form_body.html`'s submit interceptor routes to the
  correct modal based on `is_retroactive` and the current
  `retroactive_confirmed` state. `data-save-confirmed` on
  `#pattern-form-body` bypasses the interceptor on the final resubmit.

## HTMX and Alpine conventions

These are the sharp edges. Read carefully.

### HTMX

- Views branch on `request.headers.get("HX-Request") == "true"`. The
  same URL serves both HTMX clients (return a fragment) and plain POSTs
  (redirect). Never require HTMX.
- HTMX reads `hx-post` / `hx-target` when it **processes** an element,
  not at request time. When Alpine binds those attributes dynamically,
  call `htmx.process(form)` in `$nextTick` after Alpine updates the
  attributes, or the request goes to the wrong URL.
- For fragment responses that need context processors (`perms`,
  `is_management`, `app_name`), use `render_to_string(template, context,
  request=request)`. Without `request=`, `RequestContext` isn't
  populated and template conditionals silently evaluate to false.
- For out-of-band swaps, return multiple fragments concatenated in one
  `HttpResponse`. HTMX takes the first non-oob element as the primary
  swap and processes the rest as `hx-swap-oob`.
- `HX-Retarget` + `HX-Reswap` headers redirect the swap target. Used for
  validation failures that need to render inside a modal instead of
  replacing the main content.
- **Content inserted by an HTMX swap needs Alpine re-init.** `base.html`
  has a global listener that calls `Alpine.initTree(root)` on every
  `htmx:afterSwap`. `initTree` is idempotent.

### Alpine

- **Register every component in a `<script>` block that includes once
  per page**, typically inside a partial (`_page_state.html` for the
  home page; the pattern form registers its own components inside
  `_pattern_form_body.html`). Do not scatter `Alpine.data(...)` calls.
- **Never use `x-model` on a form field whose initial value is
  server-rendered.** Alpine writes state to the DOM on init, which
  clobbers Django's rendered value. Symptoms: the field is empty on
  first interaction despite being filled in HTML, or a server-error
  re-render loses the submitted value. This has cost us hours.
- **For server-rendered forms, mirror one-way:**
  - State is declared as `addEmployeeFirstName: "",` etc.
  - `init()` reads the DOM into state: `this.addEmployeeFirstName =
    read("first_name");`
  - Each input gets `@input="addEmployeeFirstName = $event.target.value"`.
  - State is never written back to the DOM except when explicitly
    clearing the form after a successful save.
- **For modals whose state comes from data attributes** (e.g. override
  modal opened by a cell button), `x-model` is fine — no server-rendered
  value to clobber.
- **Never use `@htmx:afterRequest` or `@htmx:beforeSwap` as Alpine
  directives.** The `:` is parsed as a modifier separator; the listener
  never attaches. Instead, register native listeners in the component's
  `init()`:

      this.$el.addEventListener("htmx:afterRequest", (e) => {
          if (e.detail.elt?.id === "override-form") { /* ... */ }
      });

  Route by `e.detail.elt.id` so one handler can serve multiple forms.
- **Alpine scope can be lost across HTMX swaps.** When a modal's submit
  button calls an Alpine method (`@click="handleSave"`), and the modal
  lives inside a form whose parent gets swapped mid-dispatch, the
  method can throw `this.close is not a function` or similar. The throw
  is often swallowed by Alpine's error handler (silent failure with no
  console output). This is why Pattern B modals exist — see below.
  Diagnose by wrapping the method with logging and checking
  `data.close !== undefined` before trusting it.

### Modal patterns

Two patterns coexist. Both use `.modal-animate` (defined in `base.html`)
for enter/exit transitions via `@starting-style`. Don't reimplement.

**Don't put Tailwind's `top-1/2 left-1/2 -translate-x-1/2
-translate-y-1/2` on the dialog.** The `.modal-animate` CSS handles
positioning, and the utility transforms conflict with the scale
animation.

#### Pattern A — Alpine-driven (older)

Used by `_add_employee.html`, `_day.html`, `_print.html`,
`_override.html`, `_deactivate.html`, `_delete_pattern_confirm.html`.

    <dialog
        id="..."
        x-data="{ closing: false }"
        x-effect="
            if (isOpen && !$el.open) $el.showModal();
            if (!isOpen && $el.open && !closing) {
                closing = true;
                setTimeout(() => { $el.close(); closing = false; }, 200);
            }
        "
        :class="{ 'is-closing': closing }"
        @cancel.prevent="isOpen = false"
        @close="isOpen = false"
        class="modal-animate fixed rounded-xl p-0 backdrop:bg-black/40 w-full max-w-sm m-0"
    >

- Each dialog owns its own `closing` flag. Don't put the delay logic
  in a parent component method.
- `@cancel.prevent` routes ESC through the animated close.
- **When to use:** modal state is Alpine-driven, trigger is an Alpine
  `@click` inside a non-swapped region, form fields come from `x-model`
  or data attributes. Fine for admin-style modals that live outside the
  pattern form.
- **Fragile when:** the modal is included from inside an HTMX-swappable
  region and its submit button calls an Alpine method on the parent
  component.

#### Pattern B — native-button (newer, preferred for new work)

Used by `_retroactive_confirm.html`, `_confirm_discard.html`,
`_confirm_save_details.html`, `_cancel_deactivation_confirm.html`,
`_confirm_save_pattern.html`, `_week_picker.html`.

    <dialog
        id="my-modal"
        aria-labelledby="my-modal-title"
        class="modal-animate fixed rounded-xl p-0 backdrop:bg-black/40 w-full max-w-sm m-0"
    >
        <h2 id="my-modal-title" class="...">Title</h2>
        <button
            type="button"
            onclick="window.__closeMyModal?.()"
            class="..."
        >Cancel</button>
        <button
            type="button"
            onclick="window.__confirmMyModal?.()"
            class="..."
        >Confirm</button>
    </dialog>
    <script>
        (() => {
            if (window.__myModalWired) return;
            window.__myModalWired = true;
            const dialogEl = () => document.getElementById("my-modal");
            const dismiss = () => {
                const d = dialogEl();
                if (!d || !d.open || d.classList.contains("is-closing")) return;
                d.classList.add("is-closing");
                setTimeout(() => { d.close(); d.classList.remove("is-closing"); }, 200);
            };
            window.__openMyModal = () => { const d = dialogEl(); if (d && !d.open) d.showModal(); };
            window.__closeMyModal = dismiss;
            window.__confirmMyModal = () => { /* ... */ dismiss(); };
            document.addEventListener("keydown", (e) => {
                if (e.key !== "Escape") return;
                const d = dialogEl();
                if (d && d.open) { e.preventDefault(); dismiss(); }
            }, true);
        })();
    </script>

- State lives entirely on the DOM element (`classList.contains("is-closing")`)
  and in `data-*` attributes or form fields. No Alpine state on the
  dialog itself.
- Buttons use native `onclick`, not Alpine `@click`. This sidesteps the
  Alpine-scope-lost-during-HTMX-swap failure mode entirely.
- Dismiss helpers exposed on `window.__closeXxx` / `window.__confirmXxx`
  for other scripts to call (e.g. the submit interceptor chains through
  two modals by calling the next one's `window.__openXxx`).
- Guard with a `window.__myModalWired` flag so the script block is a
  no-op if HTMX ever re-inserts the modal (idempotent).
- **When to use:** new modals, especially any triggered from inside
  `_pattern_form_body.html` or other HTMX-swappable regions. Also
  preferred when a submit button must call out to `window` regardless
  of Alpine state.
- **Note:** some Pattern B modals (e.g. `_week_picker.html`) use Alpine
  for their internal state (calendar view, selected week) but keep the
  dialog's open/close on `window.__openXxx`/`window.__closeXxx` and
  don't trust `this.$el` inside close helpers — always query the dialog
  via `document.getElementById`. See `_week_picker.html` for the
  reference implementation.

#### Confirmation modals

A common sub-class. All use Pattern B and follow the same shape:

| Modal | Trigger | Confirm behavior |
|---|---|---|
| `_confirm_discard.html` | Any Cancel button that would abandon unsaved edits | Navigates to `href` |
| `_confirm_save_pattern.html` | Non-retroactive pattern Save | Sets `saveConfirmed`, resubmits |
| `_retroactive_confirm.html` | Retroactive pattern Save | Sets `retroactive_confirmed` + `saveConfirmed`, resubmits |
| `_confirm_save_details.html` | Details-page Save | Sets `confirmed`, resubmits |
| `_cancel_deactivation_confirm.html` | Details-page "Cancel deactivation" | Submits hidden sibling form |
| `_delete_pattern_confirm.html` | Any Delete-pattern button | Submits hidden form |
| `_deactivate.html` | Any "Set Last Day" button | Whole modal is the form; submit posts last_day |

Wired via `openConfirmDiscardModal(href)`, `window.__openConfirmSavePattern(name)`,
`openDeactivateModal(button)` (data-attribute driven), etc. New
confirmations should follow the same shape — verify the modal file
matches the pattern above before adding one.

### Tooltips vs errors

Two distinct visual languages:

- **Tooltips** — gray italic, small, right-aligned in the field's label
  row. Neutral guidance ("Please enter a first name", "That doesn't
  look like an email"). Appear only after the user has interacted with
  the form (`dirty` flag). Suppress while the field is valid.
- **Errors** — red, under the field. Come from the server (Django form
  validation). Never produced client-side.

Client-side validation never blocks submission from the user's point of
view; it disables the Save button as a hint. The server is always the
final authority.

## Testing

- `unittest` TestCase. Factories in `schedule/tests/factories.py`.
- Every test class that hits a template needs
  `@override_settings(CACHES=_LOCMEM_CACHES)` because the cache is Redis
  in prod.
- Test files by concern:
  - `test_home.py` — schedule view
  - `test_employee.py` — employee reading page
  - `test_details.py` — employee details page (/details/)
  - `test_overrides.py` — shift and day overrides
  - `test_print.py` — print view
  - `test_notifications.py` — transactional emails
  - `test_models.py`, `test_helpers.py`, `test_cycle.py`
  - `test_middleware.py`, `test_signals.py`
  - `test_views_edges.py` — auth/permission edge cases across views
  - `test_settings.py` — settings page
  - `test_pattern_forms.py` — change/add form and preview
  - `test_pattern_edit.py` — pattern edit page
  - `test_pattern_alignment.py` — cycle/calendar alignment
  - `test_pattern_resolution.py` — `_pattern_for_week`
  - `test_delete_pattern.py` — delete_pattern view
  - `test_week_picker.py` — calendar week picker
  - `test_employees_for_week.py` — employment-period overlap query
- Notifications are tested with
  `@patch("schedule.notifications.send_email")`.
- The HTMX branches of `set_override`, `set_day_override`, and
  `add_employee` currently have **no test coverage**. If you touch them,
  consider adding tests using `self.client.post(url, data,
  HTTP_HX_REQUEST="true")`.
- The pattern form's client-side JS (value cache, submit interceptor,
  week picker) has no Django-side coverage. Verify manual browser
  behavior when touching it.

## Gotchas and things we've learned the hard way

- **`collectstatic` before `test`.** Missing manifest entries take down
  every page. Pre-commit script handles it; if you run tests manually,
  run collectstatic first.
- **The `.env` file is load-bearing.** `settings.py` reads
  `APP_NAME`, `SITE_URL`, `POSTGRES_*`, `REDIS_URL`, `RESEND_API_KEY`,
  `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`.
  Missing keys fail at startup, not at first use.
- **Favicon cache is aggressive.** After changing `favicon.ico` or
  `favicon.svg`, hard refresh or open a private window. Logging out and
  back in also refreshes the tab in most browsers. Don't chase this as
  a bug.
- **Safari's native `<input type="date">` has no calendar picker.** It
  shows three inline segments. This is Safari's UI, not a bug in our
  code. Chrome/Edge/Firefox show a picker. If someone wants uniform
  picker UI, the answer is a library (Flatpickr), not CSS hacks.
- **`home.html` renders messages via an out-of-band swap on HTMX
  saves.** If you add a new HTMX success path that sets a
  `messages.success()`, include the `_messages.html` fragment in the
  response (see `add_employee` in `views.py` for the pattern).
- **`make_employee()` defaults to `with_pattern=False`.** See Factories
  section. This is the #1 test-writing gotcha.
- **Alpine `@click` on submit buttons inside HTMX-swappable forms can
  lose scope.** Symptom: the method runs but throws `this.X is not a
  function`; Alpine swallows the error and the action silently no-ops.
  Use Pattern B modals (native `onclick` + `window.__xxx` helpers) for
  anything inside the pattern form. Diagnose by wrapping the method
  with `console.log(this)` and checking whether the expected properties
  are on `this`.
- **`_grid_weeks_for_form` has two modes.** Calendar mode (change/add)
  looks up which pattern covers each panel's calendar week. Direct
  mode (edit) pulls from the pattern's own cycle offsets. They produce
  identical results for non-truncated patterns. If you touch it, make
  sure both modes still hold.
- **Cycle-offset arithmetic must be calendar-anchored, not offset-
  anchored.** `_cycle_offset(week_start, cycle_weeks)` uses
  `CYCLE_EPOCH` as the anchor. Prefill, save, and notification-diff all
  depend on this being consistent. Don't touch the anchor without
  understanding the blast radius.

## What NOT to do

- Don't add a CDN link for HTMX or Alpine. Vendor under `static/js/`.
- Don't add `x-model` to a form field whose value comes from a Django
  template variable.
- Don't use `@htmx:` as an Alpine directive.
- Don't put animated modal logic in a parent component method. Use the
  local `x-data="{ closing: false }"` (Pattern A) or the DOM-managed
  Pattern B with `window.__closeXxx`.
- Don't add a new modal using Pattern A if it will be triggered from
  inside `_pattern_form_body.html` or another HTMX-swappable region.
  Use Pattern B.
- Don't add new tests without the `@override_settings(CACHES=...)`
  decorator when the test loads any template.
- Don't add `make_employee()` calls without thinking about whether the
  test needs a pattern (`with_pattern=True` or `cycle_weeks=N`).
- Don't build multi-tenancy or licensing until those branches are
  explicitly started. Don't design in ways that block them, either —
  see the "keep in mind" note below.
- Don't reformat large unrelated chunks of a file in a bug-fix commit.
  Keep diffs surgical.

## Multi-tenancy and beyond: what to keep in mind

Even though we're not building it, a few habits preserve the ability to
add it later:

- **Design new domain models with a company FK in mind.** Do not add
  the FK until a `Company` model exists — nothing to point at. But when
  you design a model's schema, ask "does this belong to a company or
  a team in the future?" and shape the fields so adding the FK later
  is a one-column migration, not a restructure.
- **When the Company model does land**, every existing domain model
  gets the FK in the same migration batch. Retrofitting a foreign key
  to populated tables is the expensive part; doing it while they're
  small is cheap.
- **New queryset helpers take a `company` parameter in their signature.**
  Even if the caller passes a single default company today.
- **`app_name` resolution is centralized** in
  `work_schedule/context_processors.py`. When multi-tenancy lands, this
  is the one chokepoint to change — resolve from `request.company`.
- **Emails won't have a request.** When `send_email` needs a company,
  it'll take one as a parameter rather than reading from a context.
- **The week picker renders 7-day bands (Mon–Sun) even though the
  schedule only uses Mon–Sat.** This is deliberate: a future
  `tenant.work_days` array can drive the width without a rewrite.

## Quick reference: where things live

| I want to... | Look at... |
|---|---|
| Add a helper to the schedule logic | `schedule/views.py`, appropriate section |
| Add a field to Employee | `schedule/models.py`, `schedule/forms.py`, `schedule/views.py::_handle_identity_post` |
| Add a new page under schedule | `schedule/templates/schedule/`, add route in `schedule/urls.py` |
| Add a new modal | `schedule/templates/schedule/modals/`, follow Pattern B (see Modal patterns) |
| Add a new confirmation modal | `schedule/templates/schedule/modals/_confirm_*.html`, follow the confirmation matrix above |
| Add a new reusable partial | `schedule/templates/schedule/partials/`, use `{% include %}` |
| Add a new test | `schedule/tests/test_*.py`, use factories |
| Change the pattern form (change/add/edit) | `_pattern_form_body.html`, `pattern_form.html`, `_week_picker.html` — see "Pattern form domain" |
| Add a new transactional email | `templates/emails/` (HTML + txt), `schedule/notifications.py` sender, register in `accounts/management/commands/send_test_emails.py` |
| Debug a template | `uv run python manage.py shell` then `render_to_string` the template manually |
| Understand past design decisions | `docs/design/SESSIONS.md` |
| Find stale template paths | `grep -rn '"schedule/_' schedule/views.py` |