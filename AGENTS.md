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

### Key models (`schedule/models.py`)

- `Employee` — title, name, role FK, email, optional User link,
  `start_date`, `last_day`, `is_active`
- `EmploymentPeriod` — one continuous stretch of employment per
  employee. `end_date` is **exclusive** (first day NOT employed)
- `ShiftPattern` — a snapshot of an employee's default schedule for a
  given `effective_from` (Monday-aligned) through the day before the
  next pattern. Holds `cycle_weeks` (1–4)
- `Shift` — one cell of a pattern: `(pattern, week_offset, day)` →
  start/end. Missing combinations mean OFF
- `ShiftOverride` — per-employee per-date override, `is_off` flag or
  substitute times
- `DayOverride` — whole-date status (Closed, Holiday) affecting every
  employee

### Template layout

    templates/                          # project-level
      base.html                         # global shell, htmx+alpine wiring
      partials/                         # cross-app partials
        _messages.html
      emails/                           # transactional emails (HTML + txt)

    schedule/templates/schedule/        # schedule app pages and pieces
      home.html, employee_defaults.html,
      settings.html, print_schedule.html
      partials/                         # composed into pages
        _page_header.html, _page_state.html,
        _schedule_table.html, _schedule_row.html,
        _employee_header.html, _identity_form.html,
        _pattern_strip.html, _defaults_form.html, _saved_patterns.html
      modals/                           # self-contained, permission-gated
        _override.html, _day.html, _add_employee.html,
        _add_employee_form.html, _print.html,
        _deactivate.html, _retroactive_confirm.html,
        _delete_pattern_confirm.html
      icons/                            # reusable SVG includes
        _printer.html

Pages orchestrate includes. Partials are composed into pages. Modals
carry their own markup and animation and are gated on permissions in
the including page.

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
  multi-week cycle a given date falls on.

### Django templates

- `{# ... #}` is **single-line only**. It does not span newlines; a
  multi-line comment with `{# ... #}` renders literally. Use
  `{% comment %} ... {% endcomment %}` for anything multi-line.
- Server-rendered values in form fields matter. See HTMX/Alpine section
  below before touching any form.

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

### Alpine

- **Register every component in a `<script>` block that includes once
  per page**, typically inside a partial (`_page_state.html`). Do not
  scatter `Alpine.data(...)` calls.
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
  value to clobber. `openOverride(d)` populates state from
  `d.start`, `d.end`, etc., and `x-model` binds the input.
- **Never use `@htmx:afterRequest` or `@htmx:beforeSwap` as Alpine
  directives.** The `:` is parsed as a modifier separator; the listener
  never attaches. Instead, register native listeners in the component's
  `init()`:

      this.$el.addEventListener("htmx:afterRequest", (e) => {
          if (e.detail.elt?.id === "override-form") { /* ... */ }
      });

  Route by `e.detail.elt.id` so one handler can serve multiple forms.
- **`htmx:afterSwap` needs Alpine re-init.** HTMX inserts new DOM but
  Alpine doesn't walk it automatically. `base.html` has a global
  listener that calls `Alpine.initTree(root)` on every swap.
  `initTree` is idempotent.

### Modal transition pattern

Every animated `<dialog>` follows this exact shape:

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

- The `.modal-animate` class (defined in `base.html`) provides enter and
  exit transitions via `@starting-style`. Don't reimplement.
- Each dialog owns its own `closing` flag. Don't put the delay logic in
  a parent component method.
- `@cancel.prevent` routes ESC through the animated close.
- Don't put Tailwind's `top-1/2 left-1/2 -translate-x-1/2
  -translate-y-1/2` on the dialog — the `.modal-animate` CSS handles
  positioning, and the utility transforms conflict with the scale
  animation.

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
- Test files by concern: `test_home.py` for the schedule view,
  `test_employee.py` for the employee page, `test_overrides.py` for
  overrides, `test_print.py` for the print view, `test_notifications.py`
  for emails, `test_models.py`, `test_helpers.py`, `test_cycle.py`,
  `test_middleware.py`, `test_signals.py`, `test_views_edges.py`.
- Notifications are tested with `@patch("schedule.notifications.send_email")`.
- The HTMX branches of `set_override`, `set_day_override`, and
  `add_employee` currently have **no test coverage**. If you touch them,
  consider adding tests using `self.client.post(url, data,
  HTTP_HX_REQUEST="true")`.

## Gotchas and things we've learned the hard way

- **`collectstatic` before `test`.** Missing manifest entries take down
  every page. Pre-commit script handles it; if you run tests manually,
  run collectstatic first.
- **The `.env` file is load-bearing.** `settings.py` reads
  `APP_NAME`, `SITE_URL`, `POSTGRES_*`, `REDIS_URL`, `RESEND_API_KEY`,
  `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`.
  Missing keys fail at startup, not at first use.
- **Favicon cache is aggressive.** After changing `favicon.ico`, hard
  refresh or open a private window. Logging out and back in also
  refreshes the tab in most browsers. Don't chase this as a bug.
- **Safari's native `<input type="date">` has no calendar picker.** It
  shows three inline segments. This is Safari's UI, not a bug in our
  code. Chrome/Edge/Firefox show a picker. If someone wants uniform
  picker UI, the answer is a library (Flatpickr), not CSS hacks.
- **Never touch `ShiftPattern` with a runtime slide in an HTMX fragment
  response.** Pattern changes need a full re-render to keep the pattern
  list and strip in sync. Return the whole affected region or redirect.
- **The `is_management` context processor** lives in
  `accounts/context_processors.py` and is registered globally. It's
  available in every template via `RequestContext`. Fragment responses
  using `render_to_string` need `request=request` for it to be
  populated.
- **`home.html` renders messages via an out-of-band swap on HTMX
  saves.** If you add a new HTMX success path that sets a
  `messages.success()`, include the `_messages.html` fragment in the
  response (see `add_employee` in `views.py` for the pattern).

## What NOT to do

- Don't add a CDN link for HTMX or Alpine. Vendor under `static/js/`.
- Don't add `x-model` to a form field whose value comes from a Django
  template variable.
- Don't use `@htmx:` as an Alpine directive.
- Don't put animated modal logic in a parent component method. Use the
  local `x-data="{ closing: false }"` pattern.
- Don't add new tests without the `@override_settings(CACHES=...)`
  decorator when the test loads any template.
- Don't build multi-tenancy or licensing until those branches are
  explicitly started. Don't design in ways that block them, either —
  see the "keep in mind" note below.
- Don't reformat large unrelated chunks of a file in a bug-fix commit.
  Keep diffs surgical.

## Multi-tenancy and beyond: what to keep in mind

Even though we're not building it, a few habits preserve the ability to
add it later:

- **Every new domain model gets a `company` FK when it's created.**
  Even if there's only one company for now, retrofitting a foreign key
  to existing data is the expensive part.
- **New queryset helpers take a `company` parameter in their signature.**
  Even if the caller passes a single default company today.
- **`app_name` resolution is centralized** in
  `work_schedule/context_processors.py`. When multi-tenancy lands, this
  is the one chokepoint to change — resolve from `request.company`.
- **Emails won't have a request.** When `send_email` needs a company,
  it'll take one as a parameter rather than reading from a context.

## Quick reference: where things live

| I want to... | Look at... |
|---|---|
| Add a helper to the schedule logic | `schedule/views.py`, appropriate section |
| Add a field to Employee | `schedule/models.py`, `schedule/forms.py`, `schedule/views.py::_handle_identity_post` |
| Add a new page under schedule | `schedule/templates/schedule/`, add route in `schedule/urls.py` |
| Add a new modal | `schedule/templates/schedule/modals/`, include from a page, follow the modal pattern above |
| Add a new reusable partial | `schedule/templates/schedule/partials/`, use `{% include %}` |
| Add a new test | `schedule/tests/test_*.py`, use factories |
| Add a new transactional email | `templates/emails/` (HTML + txt), `schedule/notifications.py` sender, register in the test command at `accounts/management/commands/send_test_emails.py` |
| Debug a template | `uv run python manage.py shell` then `render_to_string` the template manually |
| Find stale template paths | `grep -rn '"schedule/_' schedule/views.py` |