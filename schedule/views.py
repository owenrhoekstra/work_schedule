"""Views and helpers for the schedule app.

File layout, top to bottom:

    1. Constants
    2. Decorators
    3. Parsing and formatting helpers
    4. Week helpers
    5. Pattern and cycle helpers
    6. Employment helpers
    7. Shift display helpers
    8. Schedule building
    9. Views — schedule
    10. Views — employee page
    11. Views — overrides
    12. Views — settings
    13. Views — print

Sections 3–8 are pure helpers: no request objects, no HTTP concerns.
Sections 9–13 are the actual views.
"""

import io
from datetime import date, datetime, timedelta
from functools import wraps
from types import SimpleNamespace

import qrcode
import qrcode.image.svg
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Min, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import notifications
from .forms import EmployeeForm
from .models import (
    DayOverride,
    Employee,
    EmploymentPeriod,
    Role,
    Shift,
    ShiftOverride,
    ShiftPattern,
    Title,
)

# ---------------------------------------------------------------------------
# 1. Constants
# ---------------------------------------------------------------------------

DAYS = [0, 1, 2, 3, 4, 5]
DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
DAY_LABELS_FULL = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
]
WEEK_LABELS = ["A", "B", "C", "D"]
MAX_CYCLE_WEEKS = 4
MAX_PRINT_WEEKS = 4

_TIME_FORMATS = (
    "%H:%M",
    "%H:%M:%S",
    "%H%M",
    "%I:%M %p",
    "%I:%M%p",
    "%I %p",
    "%I%p",
    "%I:%M:%S %p",
    "%I:%M:%S%p",
    "%I",
)


# ---------------------------------------------------------------------------
# 2. Decorators
# ---------------------------------------------------------------------------


def management_required(view):
    """Allow superusers and members of the Management group."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if user.is_superuser or user.groups.filter(name="Management").exists():
            return view(request, *args, **kwargs)
        raise PermissionDenied

    return wrapper


# ---------------------------------------------------------------------------
# 3. Parsing and formatting helpers
# ---------------------------------------------------------------------------


def _parse_time(value):
    """Parse a user-entered time string. Returns None if empty.

    Raises ValueError if the string can't be parsed.
    """
    value = (value or "").strip()
    if not value:
        return None
    normalized = value.replace(".", ":").upper()
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(normalized, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Could not understand the time {value!r}.")


def _format_duration(td):
    """Format a timedelta as 'Hh MMm'."""
    total_minutes = int(td.total_seconds() // 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}h {minutes:02d}m"


def _format_time_12(t):
    """Format a time as '9:00 AM' (no leading zero on the hour)."""
    s = t.strftime("%I:%M %p")
    return s[1:] if s.startswith("0") else s


def _ordinal(n):
    """1 -> '1st', 2 -> '2nd', 3 -> '3rd', 4 -> '4th', 11 -> '11th', ..."""
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


# ---------------------------------------------------------------------------
# 4. Week helpers
# ---------------------------------------------------------------------------


def _week_start(d):
    """Return the Monday of the week containing d."""
    return d - timedelta(days=d.weekday())


def _week_title_for(week_start):
    """Human title for a week, with ordinal day and year when it differs."""
    current_week = _week_start(timezone.localdate())
    day_with_ordinal = _ordinal(week_start.day)
    if week_start.year == current_week.year:
        return f"Week of {week_start.strftime('%B')} {day_with_ordinal}"
    return f"Week of {week_start.strftime('%B')} {day_with_ordinal}, {week_start.year}"


def _week_range_label(weeks):
    """Build a header label spanning one or more weeks.

    One week: "Week of October 5th"
    Multiple: "Week of October 5th – October 19th"
    """
    if not weeks:
        return ""
    first_title = weeks[0]["week_title"]
    if len(weeks) == 1:
        return first_title
    last_title = weeks[-1]["week_title"]
    # Drop the "Week of " prefix from the last title so the range reads
    # as a span rather than two back-to-back week titles.
    last_short = last_title.removeprefix("Week of ")
    return f"{first_title} – {last_short}"


def _parse_week_param(request):
    """Read ?week=YYYY-MM-DD and return that week's Monday, or None."""
    raw = request.GET.get("week", "").strip()
    if not raw:
        return None
    try:
        d = date.fromisoformat(raw)
    except ValueError:
        return None
    return _week_start(d)


def _earliest_week():
    """Monday of the week containing the oldest employment period start."""
    earliest = EmploymentPeriod.objects.aggregate(d=Min("start_date"))["d"]
    if earliest is None:
        return None
    return _week_start(earliest)


def _home_url_for(date_):
    """Redirect to home, scrolled to the week containing date_."""
    return f"{reverse('home')}?week={_week_start(date_).isoformat()}"


# ---------------------------------------------------------------------------
# 5. Pattern and cycle helpers
# ---------------------------------------------------------------------------


def _pattern_for_week(employee, week_start):
    """The ShiftPattern active for the week starting week_start.

    Returns the pattern whose [effective_from, effective_to) range
    contains week_start. effective_to is exclusive and None means
    open-ended.

    If multiple patterns match — possible during the transition to
    explicit end dates, when the old form can still create overlapping
    patterns — the one with the greatest effective_from wins. This
    preserves the previous "latest pattern" behavior for that legacy
    state so nothing regresses before the form is rewritten.

    Iterates over the (prefetched) patterns relation in Python so the
    schedule render doesn't fire one query per employee. Returns None
    if no pattern covers the week.
    """
    candidates = [
        p
        for p in employee.patterns.all()
        if p.effective_from <= week_start
        and (p.effective_to is None or week_start < p.effective_to)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.effective_from)


def _cycle_offset(week_start, cycle_weeks):
    """Which week of a cycle_weeks-long cycle the given week falls on.

    Anchored at settings.CYCLE_EPOCH. Returns 0 for cycle_weeks <= 1
    (single-week pattern; no offset within cycle).
    """
    if cycle_weeks <= 1:
        return 0
    weeks_since_epoch = (week_start - settings.CYCLE_EPOCH).days // 7
    return weeks_since_epoch % cycle_weeks


def _week_offset_for(week_start, pattern):
    """Which week of this pattern's cycle the given week falls on."""
    return _cycle_offset(week_start, pattern.cycle_weeks)


def _calendar_aligned_shifts(employee, effective_from, cycle_weeks):
    """Baseline shift map for the notification diff, keyed by target offset.

    Returns {(target_offset, day): Shift} capturing what the schedule
    displayed for calendar weeks effective_from + 7*i (i = 0..cycle_weeks-1)
    BEFORE a mutation, translated into the target pattern's cycle-offset
    space.

    Uses calendar-week indexing (not source-pattern offsets) so the diff
    is meaningful even when a pattern ends mid-form and a later pattern
    takes over, or when effective_from isn't congruent with CYCLE_EPOCH.
    """
    baseline = {}
    base_target_offset = _cycle_offset(effective_from, cycle_weeks)
    for cal_offset in range(cycle_weeks):
        week_start = effective_from + timedelta(weeks=cal_offset)
        source = _pattern_for_week(employee, week_start)
        if not source:
            continue
        source_offset = _week_offset_for(week_start, source)
        target_offset = (base_target_offset + cal_offset) % cycle_weeks
        for s in source.shifts.all():
            if s.week_offset == source_offset:
                baseline[(target_offset, s.day)] = s
    return baseline


def _last_week_of(pattern):
    """The Monday of the last week this pattern covers, or None if open-ended.

    `effective_to` is exclusive — the first week *not* covered — so the
    last covered week starts seven days earlier. Used for display copy
    only; resolution logic uses `effective_to` directly.
    """
    if pattern is None or pattern.effective_to is None:
        return None
    return pattern.effective_to - timedelta(days=7)


# ---------------------------------------------------------------------------
# 6. Employment helpers
# ---------------------------------------------------------------------------


def _employees_for_week(week_start):
    """Employees with any employment period overlapping this week.

    Both halves of the overlap test are wrapped in a single filter() so
    they apply to the same joined `periods` row. Chaining two filter()
    calls on the multi-valued relation would create separate joins,
    letting an employee with a closed period and a later reactivation
    period appear in the gap between them.
    """
    week_end = week_start + timedelta(days=5)
    return (
        Employee.objects.filter(
            Q(periods__start_date__lte=week_end)
            & (Q(periods__end_date__isnull=True) | Q(periods__end_date__gt=week_start))
        )
        .distinct()
        .select_related("title", "role")
        .prefetch_related("periods", "patterns__shifts")
        .order_by("role__display_order", "role__name", "start_date")
    )


def _employed_dates(employee, week_dates):
    """Set of dates in week_dates covered by any employment period.

    A period covers d if start_date <= d < end_date (end_date exclusive).
    end_date=None means currently employed.
    """
    covered = set()
    for period in employee.periods.all():
        for d in week_dates:
            if period.start_date <= d and (
                period.end_date is None or period.end_date > d
            ):
                covered.add(d)
    return covered


# ---------------------------------------------------------------------------
# 7. Shift display helpers
# ---------------------------------------------------------------------------


def _shift_display(shift):
    """Human-readable shift display, or None."""
    if shift is None:
        return None
    return f"{_format_time_12(shift.start_time)} – {_format_time_12(shift.end_time)}"


def _cell_display(employee, d):
    """What the schedule cell shows for this employee on this date.

    Overrides take precedence; otherwise the default from the pattern
    active that week.
    """
    override = employee.overrides.filter(date=d).first()
    if override:
        if override.is_off:
            return "OFF"
        return (
            f"{_format_time_12(override.start_time)} – "
            f"{_format_time_12(override.end_time)}"
        )

    week_start = _week_start(d)
    pattern = _pattern_for_week(employee, week_start)
    if pattern is None:
        return "OFF"

    offset = _week_offset_for(week_start, pattern)
    day = d.weekday()
    default = pattern.shifts.filter(week_offset=offset, day=day).first()
    if default:
        return (
            f"{_format_time_12(default.start_time)} – "
            f"{_format_time_12(default.end_time)}"
        )
    return "OFF"


def _diff_pattern_shifts(old_shifts, new_shifts, cycle_weeks):
    """List change dicts comparing two shift snapshots.

    `old_shifts` and `new_shifts` are dicts keyed by (week_offset, day).
    `cycle_weeks` is the effective cycle length — offsets at or beyond
    it are ignored.
    """
    changes = []
    keys = sorted(set(old_shifts) | set(new_shifts), key=lambda k: (k[0], k[1]))
    for key in keys:
        week_offset, day = key
        if week_offset >= cycle_weeks:
            continue

        old = old_shifts.get(key)
        new = new_shifts.get(key)
        old_display = _shift_display(old) or "OFF"
        new_display = _shift_display(new) or "OFF"

        if old_display == new_display:
            continue

        if cycle_weeks == 1:
            label = DAY_LABELS_FULL[day]
        else:
            label = f"Week {WEEK_LABELS[week_offset]} {DAY_LABELS_FULL[day]}"

        changes.append({"label": label, "old": old_display, "new": new_display})

    return changes


def _new_week_details(pattern, old_cycle, new_cycle):
    """Rows for weeks that become active when the cycle length grows.

    Reads from the freshly saved pattern so the manager sees whatever
    they put in the new weeks. Empty weeks show OFF.
    """
    if new_cycle <= old_cycle:
        return []
    shifts_by_key = {(s.week_offset, s.day): s for s in pattern.shifts.all()}
    weeks = []
    for offset in range(old_cycle, new_cycle):
        rows = [
            {
                "day": DAY_LABELS_FULL[day],
                "time": _shift_display(shifts_by_key.get((offset, day))) or "OFF",
            }
            for day in DAYS
        ]
        weeks.append({"label": f"Week {WEEK_LABELS[offset]}", "rows": rows})
    return weeks


def _pattern_summary(pattern):
    """Render-ready rows for a pattern, grouped by cycle week.

    Returns a list of dicts, one per week in the cycle:
        {"label": "A", "rows": [{"label": "Monday", "shift": <Shift or None>}, ...]}

    Used by the Saved Patterns list to show the hours inside each
    saved pattern without firing a query per pattern.
    """
    shifts_by_key = {(s.week_offset, s.day): s for s in pattern.shifts.all()}
    weeks = []
    for offset in range(pattern.cycle_weeks):
        rows = [
            {
                "label": DAY_LABELS_FULL[day],
                "shift": shifts_by_key.get((offset, day)),
            }
            for day in DAYS
        ]
        weeks.append({"label": WEEK_LABELS[offset], "rows": rows})
    return weeks


# ---------------------------------------------------------------------------
# 8. Schedule building
# ---------------------------------------------------------------------------


def _build_schedule_rows(week_start, employee_pk=None):
    """Build the render-ready rows and day headers for one week.

    Each cell carries a `kind` string used by the print view to style
    overrides, holidays, and closures differently from regular shifts:

        "day_override"  whole day marked closed/holiday
        "not_employed"  employee not yet started or already departed
        "off_override"  manager marked this day off
        "override"      manager set custom hours
        "default"       regular pattern shift
        "none"          no shift on this day (regular OFF)

    Shift overrides are batch-fetched in a single query for the whole
    week and grouped by employee in Python, so the per-employee loop
    below doesn't fire one query per row. For a multi-week print this
    is N queries per week down to 1.

    When `employee_pk` is given, only that employee's row is built.
    Used by the HTMX override path to render a single updated row
    without walking the whole roster.
    """
    week_dates = [week_start + timedelta(days=d) for d in DAYS]
    employees = list(_employees_for_week(week_start))
    if employee_pk is not None:
        employees = [e for e in employees if e.pk == employee_pk]
    day_overrides = {o.date: o for o in DayOverride.objects.filter(date__in=week_dates)}

    # One query for every override in this week, grouped by employee.
    overrides_by_employee = {}
    if employees:
        for override in ShiftOverride.objects.filter(
            employee__in=employees, date__in=week_dates
        ):
            overrides_by_employee.setdefault(override.employee_id, {})[
                override.date
            ] = override

    rows = []

    for emp in employees:
        pattern = _pattern_for_week(emp, week_start)
        offset = _week_offset_for(week_start, pattern) if pattern else 0
        defaults = (
            {s.day: s for s in pattern.shifts.all() if s.week_offset == offset}
            if pattern
            else {}
        )
        overrides = overrides_by_employee.get(emp.id, {})
        employed = _employed_dates(emp, week_dates)
        cells = []
        total = timedelta()

        for day, d in zip(DAYS, week_dates):
            day_override = day_overrides.get(d)

            if day_override:
                cells.append(
                    {
                        "date_iso": d.isoformat(),
                        "day_label": DAY_LABELS_FULL[day],
                        "date_label": f"{d.strftime('%b')} {d.day}",
                        "start": None,
                        "end": None,
                        "state_class": "text-brand-indigo font-medium",
                        "display": day_override.get_status_display(),
                        "has_override": False,
                        "is_employed": False,
                        "kind": "day_override",
                    }
                )
                continue

            if d not in employed:
                cells.append(
                    {
                        "date_iso": d.isoformat(),
                        "day_label": DAY_LABELS_FULL[day],
                        "date_label": f"{d.strftime('%b')} {d.day}",
                        "start": None,
                        "end": None,
                        "state_class": "text-gray-300",
                        "display": "—",
                        "has_override": False,
                        "is_employed": False,
                        "kind": "not_employed",
                    }
                )
                continue

            default_shift = defaults.get(day)
            override = overrides.get(d)

            if override and override.is_off:
                state = "off_override"
                start = end = None
            elif override:
                state = "override"
                start, end = override.start_time, override.end_time
            elif default_shift:
                state = "default"
                start, end = default_shift.start_time, default_shift.end_time
            else:
                state = "none"
                start = end = None

            if start and end:
                total += datetime.combine(date.min, end) - datetime.combine(
                    date.min, start
                )

            if state in ("override", "off_override"):
                state_class = "text-brand-coral"
            elif state == "default":
                state_class = "text-brand-indigo"
            else:
                state_class = "text-gray-400"

            display = (
                f"{_format_time_12(start)} - {_format_time_12(end)}"
                if start and end
                else "OFF"
            )

            cells.append(
                {
                    "date_iso": d.isoformat(),
                    "day_label": DAY_LABELS_FULL[day],
                    "date_label": f"{d.strftime('%b')} {d.day}",
                    "start": start,
                    "end": end,
                    "state_class": state_class,
                    "display": display,
                    "has_override": override is not None,
                    "is_employed": True,
                    "kind": state,
                }
            )

        rows.append(
            {
                "employee": emp,
                "cells": cells,
                "total_hours": _format_duration(total),
                "cycle_label": (
                    WEEK_LABELS[offset] if pattern and pattern.cycle_weeks > 1 else None
                ),
                "last_day": emp.last_day,
            }
        )

    day_headers = [
        {
            "label": DAY_LABELS_FULL[i],
            "date_label": f"{d.strftime('%b')} {d.day}",
            "date_iso": d.isoformat(),
            "day_status": (
                day_overrides[d].get_status_display() if d in day_overrides else ""
            ),
        }
        for i, d in enumerate(week_dates)
    ]
    return rows, day_headers


def _home_context(week_start):
    """Build the shared context for the home page."""
    current_week = _week_start(timezone.localdate())
    rows, day_headers = _build_schedule_rows(week_start)
    min_week = _earliest_week()

    return {
        "rows": rows,
        "day_headers": day_headers,
        "week_start": week_start,
        "week_title": _week_title_for(week_start),
        "prev_week": week_start - timedelta(days=7),
        "next_week": week_start + timedelta(days=7),
        "is_current_week": week_start == current_week,
        "can_go_back": min_week is None or week_start > min_week,
    }


# ---------------------------------------------------------------------------
# 9. Views — schedule
# ---------------------------------------------------------------------------


@login_required
@permission_required("schedule.view_shift", raise_exception=True)
def home(request):
    """Render the week view for the given (or current) week."""
    week_start = _parse_week_param(request) or _week_start(timezone.localdate())
    context = _home_context(week_start)
    if request.user.has_perm("schedule.add_employee"):
        context["employee_form"] = EmployeeForm()
    return render(request, "schedule/home.html", context)


@login_required
@permission_required("schedule.add_employee", raise_exception=True)
def add_employee(request):
    """Create a new employee from the modal form on the home page.

    If a matching User account already exists (by email) and isn't
    linked to another Employee, link it automatically. Optionally send
    a welcome email when `notify` is set.

    Responds two ways:

    - Plain POST → redirect to home (full page reload).
    - HTMX POST → swap the schedule table on success; swap just the
      form back into the modal on validation failure so the dialog
      stays open with errors and the user's input preserved.

    The user's viewed week is preserved across both response paths.
    The form carries a hidden `week` field seeded from the schedule
    table on the current page, so an employee added while viewing a
    past or future week lands back on that same week rather than
    jumping to the current one.
    """
    is_htmx = request.headers.get("HX-Request") == "true"

    # Resolve the viewed week from the hidden form field, falling back
    # to the current week if missing or unparseable.
    viewed_week = None
    if request.method == "POST":
        raw_week = request.POST.get("week", "").strip()
        if raw_week:
            try:
                viewed_week = _week_start(date.fromisoformat(raw_week))
            except ValueError:
                viewed_week = None
    if viewed_week is None:
        viewed_week = _week_start(timezone.localdate())

    if request.method == "POST":
        form = EmployeeForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                employee = form.save(commit=False)

                matching_user = User.objects.filter(
                    email__iexact=employee.email
                ).first()
                if (
                    matching_user
                    and not Employee.objects.filter(user=matching_user).exists()
                ):
                    employee.user = matching_user

                employee.save()

            if request.POST.get("notify"):
                ok, error = notifications.send_welcome_email(employee)
                if ok:
                    messages.success(
                        request,
                        f"{employee} added. Welcome email sent to {employee.email}.",
                    )
                else:
                    messages.warning(
                        request,
                        f"{employee} added, but the email failed: {error}",
                    )
            else:
                messages.success(request, f"{employee} added.")

            if is_htmx:
                rows, day_headers = _build_schedule_rows(viewed_week)

                # Render the table (primary swap target) and the
                # messages container (out-of-band swap). HTMX takes
                # the first non-oob element as the primary response
                # and processes the rest as oob swaps.
                table_html = render_to_string(
                    "schedule/partials/_schedule_table.html",
                    {"rows": rows, "day_headers": day_headers},
                    request=request,
                )
                messages_html = render_to_string(
                    "partials/_messages.html",
                    {"hx_oob": True},
                    request=request,
                )
                return HttpResponse(table_html + messages_html)

            # Plain POST: land on the same week the user was viewing.
            return redirect(f"{reverse('home')}?week={viewed_week.isoformat()}")

        # Form invalid. HTMX path: swap the form back into the dialog
        # as innerHTML so the modal stays open. Pass week_start so the
        # hidden field survives the round trip.
        if is_htmx:
            response = render(
                request,
                "schedule/modals/_add_employee_form.html",
                {
                    "employee_form": form,
                    "week_start": viewed_week,
                },
            )
            response["HX-Retarget"] = "#add-employee-modal"
            response["HX-Reswap"] = "innerHTML"
            return response
    else:
        form = EmployeeForm()

    context = _home_context(viewed_week)
    context["employee_form"] = form
    context["show_add_employee_modal"] = True
    return render(request, "schedule/home.html", context)


# ---------------------------------------------------------------------------
# 10. Views — employee page
# ---------------------------------------------------------------------------


def _build_default_weeks(pattern):
    """Assemble the week/row structure for the defaults editor."""
    shifts_by_key = {(s.week_offset, s.day): s for s in pattern.shifts.all()}
    weeks = []
    for week_offset in range(MAX_CYCLE_WEEKS):
        rows = [
            {
                "day": day,
                "label": DAY_LABELS_FULL[day],
                "shift": shifts_by_key.get((week_offset, day)),
            }
            for day in DAYS
        ]
        weeks.append(
            {
                "offset": week_offset,
                "label": WEEK_LABELS[week_offset],
                "rows": rows,
            }
        )
    return weeks


def _employee_page_context(request, employee, can_change=True):
    """Build the shared context for the employee reading page.

    Renders the two-column layout: employee identity on the left,
    currently-scheduled pattern on the right, full pattern history
    below in a disclosure. Read-only — identity edits live at
    /details/.

    `has_any_patterns` distinguishes the two empty states:
    - current_pattern is None, has_any_patterns True  → "Not scheduled
      this week" (employee has a history but no active coverage)
    - current_pattern is None, has_any_patterns False → "Not scheduled
      at all" (new hire; setup CTA shown)
    """
    this_week_start = _week_start(timezone.localdate())
    current = _pattern_for_week(employee, this_week_start)

    all_patterns = list(
        employee.patterns.order_by("effective_from").prefetch_related("shifts")
    )
    earliest_pk = all_patterns[0].pk if all_patterns else None

    patterns = [
        {
            "pattern": p,
            "weeks": _pattern_summary(p),
            "is_earliest": p.pk == earliest_pk,
            "last_week": _last_week_of(p),
        }
        for p in all_patterns
    ]

    current_weeks = _pattern_summary(current) if current else []
    current_cycle_label = None
    if current is not None and current.cycle_weeks > 1:
        offset = _week_offset_for(this_week_start, current)
        current_cycle_label = WEEK_LABELS[offset]

    current_last_week = _last_week_of(current)

    return {
        "employee": employee,
        "current_pattern": current,
        "current_weeks": current_weeks,
        "current_last_week": current_last_week,
        "current_cycle_label": current_cycle_label,
        "patterns": patterns,
        "has_any_patterns": bool(all_patterns),
        "can_change": can_change,
        "can_delete": request.user.has_perm("schedule.delete_shift"),
        "last_day": employee.last_day,
    }


def _render_employee_page(request, employee, can_change=True):
    """Render the employee reading page."""
    context = _employee_page_context(
        request,
        employee,
        can_change=can_change,
    )
    return render(request, "schedule/employee_defaults.html", context)


def _render_employee_details_page(request, employee, identity_form=None):
    """Render the employee details page (/details/).

    Shown on GET and on POST validation errors. Includes both the
    deactivate and confirm-discard modals — the view's context provides
    `today` for the modal's data-today.
    """
    today = timezone.localdate()
    return render(
        request,
        "schedule/employee_details.html",
        {
            "employee": employee,
            "identity_form": (
                identity_form
                if identity_form is not None
                else EmployeeForm(instance=employee)
            ),
            "last_day": employee.last_day,
            "today": today,
        },
    )


def _handle_identity_post(request, employee):
    """Save the identity form from /details/.

    On success, redirect to the reading page (employee_defaults).
    On validation error, re-render the details page with the bound
    form so errors appear inline and submitted values are preserved.

    Syncs the earliest EmploymentPeriod when start_date changes, and
    slides the earliest pattern so it stays anchored to the Monday of
    the new start week. Moving the start date earlier slides the
    earliest pattern backward; moving it later slides forward only
    when there's no collision with the next pattern.

    The write phase runs in a single transaction so the Employee,
    EmploymentPeriod, and ShiftPattern rows can't drift out of sync.
    """
    old_start = employee.start_date
    form = EmployeeForm(request.POST, instance=employee)

    if not form.is_valid():
        return _render_employee_details_page(request, employee, identity_form=form)

    new_start = form.cleaned_data["start_date"]

    if new_start != old_start:
        earliest = employee.periods.order_by("start_date").first()
        if earliest and earliest.end_date and new_start > earliest.end_date:
            form.add_error(
                "start_date",
                f"Start date can't be after this period's end date "
                f"({earliest.end_date - timedelta(days=1):%Y-%m-%d}).",
            )
            return _render_employee_details_page(request, employee, identity_form=form)

    with transaction.atomic():
        form.save()

        if new_start != old_start:
            earliest = employee.periods.order_by("start_date").first()
            if earliest:
                earliest.start_date = new_start
                earliest.save(update_fields=["start_date"])

            new_floor = _week_start(new_start)
            earliest_pattern = employee.patterns.order_by("effective_from").first()
            if earliest_pattern and earliest_pattern.effective_from != new_floor:
                if earliest_pattern.effective_from > new_floor:
                    earliest_pattern.effective_from = new_floor
                    earliest_pattern.save(update_fields=["effective_from"])
                else:
                    next_pattern = (
                        employee.patterns.filter(
                            effective_from__gt=earliest_pattern.effective_from
                        )
                        .order_by("effective_from")
                        .first()
                    )
                    if next_pattern is None or new_floor < next_pattern.effective_from:
                        earliest_pattern.effective_from = new_floor
                        earliest_pattern.save(update_fields=["effective_from"])

    messages.success(request, f"Saved {employee}.")
    return redirect("employee_defaults", pk=employee.pk)


def _grid_weeks_for_form(employee, effective_from, cycle_weeks):
    """Build the grid structure for the writing form.

    Panel i represents calendar week effective_from + 7*i, NOT the
    target pattern's cycle offset. Panel A is the week the manager
    picked; panel B is the following week; etc. Cells prefill from
    whichever pattern covers that calendar week, so the form shows
    exactly what the schedule currently displays for those weeks.

    Dedupe: when the target cycle is longer than the source pattern's
    cycle, later calendar weeks wrap around to source offsets already
    prefilled into earlier panels (e.g. target=4, source=3 → week D
    maps to source offset 0, same as week A). Those duplicate panels
    are left blank — the manager is extending the cycle, so the extra
    weeks are new territory. Sessions 6.6 (prefill modal) will layer
    optional week-by-week copy on top of this default.

    The save path translates panel index → target cycle offset, keeping
    the label-to-calendar-week mapping intact even when effective_from
    isn't congruent with CYCLE_EPOCH for the target's cycle length.
    """
    weeks = []
    seen_source_offsets = set()
    for cal_offset in range(cycle_weeks):
        shifts_by_key = {}
        if effective_from is not None:
            week_start = effective_from + timedelta(weeks=cal_offset)
            source = _pattern_for_week(employee, week_start)
            if source:
                source_offset = _week_offset_for(week_start, source)
                key = (source.pk, source_offset)
                if key not in seen_source_offsets:
                    seen_source_offsets.add(key)
                    shifts_by_key = {
                        s.day: s
                        for s in source.shifts.all()
                        if s.week_offset == source_offset
                    }
        rows = [
            {
                "day": day,
                "label": DAY_LABELS_FULL[day],
                "shift": shifts_by_key.get(day),
            }
            for day in DAYS
        ]
        weeks.append(
            {
                "offset": cal_offset,
                "label": WEEK_LABELS[cal_offset],
                "rows": rows,
            }
        )
    return weeks


def _compute_pattern_banner(employee, effective_from):
    """Describe what will happen if the user saves at effective_from.

    Copy is written for managers, not developers. It states the
    outcome of saving, names the exact weeks affected, and reassures
    about what is NOT changing. "Splitting" / "truncated" / "covering"
    jargon is avoided — the split case instead describes the old
    pattern's new end date in plain English.

    Tone: "warn" for the split case (an existing pattern's boundary
    is changing), "info" otherwise.
    """
    if effective_from is None:
        return {
            "tone": "info",
            "title": "Pick a week to begin",
            "body": "Choose the week when these hours should start.",
        }

    covering = _pattern_for_week(employee, effective_from)
    next_pattern = (
        employee.patterns.filter(effective_from__gt=effective_from)
        .order_by("effective_from")
        .first()
    )

    target_label = f"Week of {effective_from:%b} {effective_from.day}"

    # Case A: no covering pattern — this is a brand-new pattern.
    if covering is None:
        if next_pattern:
            next_label = (
                f"Week of {next_pattern.effective_from:%b} "
                f"{next_pattern.effective_from.day}"
            )
            end_week = next_pattern.effective_from - timedelta(days=7)
            end_label = f"Week of {end_week:%b} {end_week.day}"
            return {
                "tone": "info",
                "title": f"Saving will add a new pattern starting {target_label}",
                "body": (
                    f"{target_label} through {end_label} will use the new "
                    f"hours. {next_label} onward continues with the "
                    f"existing pattern. Earlier weeks are not affected."
                ),
            }
        return {
            "tone": "info",
            "title": f"Saving will add a new pattern starting {target_label}",
            "body": (
                f"{target_label} onward will use the new hours. No later "
                f"patterns exist, so this continues indefinitely."
            ),
        }

    # Case B: edit-in-place — the covering pattern starts exactly here.
    if covering.effective_from == effective_from:
        last_week = _last_week_of(covering)
        if last_week:
            last_label = f"Week of {last_week:%b} {last_week.day}"
            return {
                "tone": "info",
                "title": f"Saving will update the pattern starting {target_label}",
                "body": (
                    f"{target_label} through {last_label} will use the "
                    f"new hours. No other patterns are affected."
                ),
            }
        return {
            "tone": "info",
            "title": f"Saving will update the pattern starting {target_label}",
            "body": (
                f"{target_label} onward will use the new hours. No other "
                f"patterns are affected."
            ),
        }

    # Case C: split — the covering pattern started earlier, so it
    # will now end one week before the new pattern begins.
    old_start_label = (
        f"Week of {covering.effective_from:%b} {covering.effective_from.day}"
    )
    new_old_end = effective_from - timedelta(days=7)
    old_end_label = f"Week of {new_old_end:%b} {new_old_end.day}"

    last_week = _last_week_of(covering)
    if last_week:
        last_label = f"Week of {last_week:%b} {last_week.day}"
        body = (
            f"{target_label} through {last_label} will use the new "
            f"hours. The pattern currently in place (started "
            f"{old_start_label}) will now end on {old_end_label}. "
            f"Earlier weeks are not affected."
        )
    else:
        body = (
            f"{target_label} onward will use the new hours. The pattern "
            f"currently in place (started {old_start_label}) will now "
            f"end on {old_end_label}. Earlier weeks are not affected."
        )

    return {
        "tone": "warn",
        "title": f"Saving will change the schedule starting {target_label}",
        "body": body,
    }


def _pattern_form_context(
    request,
    employee,
    mode,
    effective_from=None,
    cycle_weeks=1,
    errors=None,
    submitted_shifts=None,
    retroactive_confirmed=False,
):
    """Shared context for the writing form GET + preview endpoints.

    No `week_options` — the week picker is a modal calendar that
    renders client-side from the dialog component. Context exposes
    `week_picker_min_iso` (the earliest selectable Monday, from
    employee.start_date) and `today_iso` for the calendar's
    today-marker; everything else is derived in JS from the Alpine
    component.
    """
    if effective_from is not None:
        sat = effective_from + timedelta(days=5)
        effective_from_label = (
            f"Week of {effective_from:%b} {effective_from.day} – {sat:%b} {sat.day}"
        )
    else:
        effective_from_label = ""

    this_week_start = _week_start(timezone.localdate())
    is_retroactive = effective_from is not None and effective_from < this_week_start

    if submitted_shifts is not None:
        weeks = []
        for offset in range(cycle_weeks):
            rows = [
                {
                    "day": day,
                    "label": DAY_LABELS_FULL[day],
                    "shift": submitted_shifts.get((offset, day)),
                }
                for day in DAYS
            ]
            weeks.append({"offset": offset, "label": WEEK_LABELS[offset], "rows": rows})
    else:
        weeks = _grid_weeks_for_form(employee, effective_from, cycle_weeks)

    return {
        "employee": employee,
        "mode": mode,
        "effective_from_iso": (effective_from.isoformat() if effective_from else ""),
        "effective_from_label": effective_from_label,
        "week_picker_min_iso": _week_start(employee.start_date).isoformat(),
        "today_iso": timezone.localdate().isoformat(),
        "cycle_weeks": cycle_weeks,
        "weeks": weeks,
        "banner": _compute_pattern_banner(employee, effective_from),
        "errors": errors or [],
        "back_url": reverse("employee_defaults", args=[employee.pk]),
        "is_retroactive": is_retroactive,
        "retroactive_confirmed": retroactive_confirmed,
    }


def _handle_pattern_form_post(request, employee, mode):
    """Shared POST handler for /schedule/change/ and /schedule/add/.

    Panel index in the POST body is a calendar-week index (panel 0 =
    calendar week effective_from, panel 1 = effective_from + 7d, ...),
    not the target pattern's cycle offset. The save loop maps each
    panel to its target offset via
    (base_target_offset + cal_offset) % cycle_weeks so the label the
    manager edited corresponds to the calendar week it will actually
    display on, even when effective_from isn't cycle-congruent.

    Grid validation collects ALL errors before re-rendering and
    preserves every successfully-parsed cell in `submitted_shifts`
    (BUG-003). Returning on the first error used to drop values for
    cells after the error and required iterative error-fixing.
    """
    raw_effective = request.POST.get("effective_from", "").strip()
    try:
        effective_from = _week_start(date.fromisoformat(raw_effective))
    except (ValueError, TypeError):
        return _render_pattern_form(
            request,
            employee,
            mode,
            errors=["Please pick a week."],
        )

    start_date_floor = _week_start(employee.start_date)
    if effective_from < start_date_floor:
        return _render_pattern_form(
            request,
            employee,
            mode,
            effective_from=effective_from,
            errors=[
                f"Effective date can't be before the employee's start "
                f"week ({start_date_floor})."
            ],
        )

    try:
        cycle_weeks = int(request.POST.get("cycle_weeks", "1"))
    except (TypeError, ValueError):
        cycle_weeks = 1
    cycle_weeks = max(1, min(MAX_CYCLE_WEEKS, cycle_weeks))

    this_week_start = _week_start(timezone.localdate())
    is_first_time = not Shift.objects.filter(pattern__employee=employee).exists()
    retroactive_confirmed = request.POST.get("retroactive_confirmed") == "1"

    if (
        effective_from < this_week_start
        and not is_first_time
        and not retroactive_confirmed
    ):
        return _render_pattern_form(
            request,
            employee,
            mode,
            effective_from=effective_from,
            cycle_weeks=cycle_weeks,
            retroactive_confirmed=retroactive_confirmed,
            errors=[
                "This date is in the past. Confirm the retroactive change to proceed."
            ],
        )

    # Validate the grid. Collect all errors before re-rendering so
    # every successfully-parsed cell survives — including cells after
    # the first error (BUG-003).
    validated_edits = {}
    submitted_shifts = {}
    errors = []
    for week_offset in range(MAX_CYCLE_WEEKS):
        for day in DAYS:
            start_key = f"week_{week_offset}_day_{day}_start"
            end_key = f"week_{week_offset}_day_{day}_end"
            if start_key not in request.POST or end_key not in request.POST:
                continue
            try:
                start = _parse_time(request.POST[start_key])
                end = _parse_time(request.POST[end_key])
            except ValueError as exc:
                errors.append(
                    f"Week {WEEK_LABELS[week_offset]} {DAY_LABELS_FULL[day]}: {exc}"
                )
                continue
            if (start is None) != (end is None):
                errors.append(
                    f"Week {WEEK_LABELS[week_offset]} "
                    f"{DAY_LABELS_FULL[day]}: set both start and end, "
                    f"or leave both empty."
                )
                continue
            if start and end:
                # Stash even invalid pairs (end <= start) so the user
                # sees what they typed and can just fix the failing
                # side. Parse-failed or half-parsed cells are dropped
                # — no clean way to represent them as a Shift-shaped
                # object for the |time filter.
                submitted_shifts[(week_offset, day)] = SimpleNamespace(
                    start_time=start, end_time=end
                )
                if end <= start:
                    errors.append(
                        f"Week {WEEK_LABELS[week_offset]} "
                        f"{DAY_LABELS_FULL[day]}: end time must be "
                        f"after start time."
                    )
                    continue
                validated_edits[(week_offset, day)] = (start, end)
            else:
                validated_edits[(week_offset, day)] = None

    if errors:
        return _render_pattern_form(
            request,
            employee,
            mode,
            effective_from=effective_from,
            cycle_weeks=cycle_weeks,
            retroactive_confirmed=retroactive_confirmed,
            submitted_shifts=submitted_shifts,
            errors=errors,
        )

    # Apply edit-or-split in a transaction.
    try:
        with transaction.atomic():
            covering = _pattern_for_week(employee, effective_from)
            if covering is None:
                next_pattern = (
                    employee.patterns.filter(effective_from__gt=effective_from)
                    .order_by("effective_from")
                    .first()
                )
                target = ShiftPattern.objects.create(
                    employee=employee,
                    effective_from=effective_from,
                    effective_to=(
                        next_pattern.effective_from if next_pattern else None
                    ),
                    cycle_weeks=cycle_weeks,
                )
                old_shifts = {}
                old_cycle = cycle_weeks
            elif covering.effective_from == effective_from:
                target = covering
                old_cycle = target.cycle_weeks
                old_shifts = _calendar_aligned_shifts(
                    employee, effective_from, cycle_weeks
                )
                if target.cycle_weeks != cycle_weeks:
                    Shift.objects.filter(
                        pattern=target, week_offset__gte=cycle_weeks
                    ).delete()
                    target.cycle_weeks = cycle_weeks
                    target.save(update_fields=["cycle_weeks"])
            else:
                old_shifts = _calendar_aligned_shifts(
                    employee, effective_from, cycle_weeks
                )
                old_end = covering.effective_to
                old_cycle = covering.cycle_weeks
                covering.effective_to = effective_from
                covering.save(update_fields=["effective_to"])
                target = ShiftPattern.objects.create(
                    employee=employee,
                    effective_from=effective_from,
                    effective_to=old_end,
                    cycle_weeks=cycle_weeks,
                )

            base_target_offset = _cycle_offset(effective_from, cycle_weeks)
            for (cal_offset, day), value in validated_edits.items():
                target_offset = (base_target_offset + cal_offset) % cycle_weeks
                if value is None:
                    Shift.objects.filter(
                        pattern=target, week_offset=target_offset, day=day
                    ).delete()
                else:
                    start, end = value
                    Shift.objects.update_or_create(
                        pattern=target,
                        week_offset=target_offset,
                        day=day,
                        defaults={"start_time": start, "end_time": end},
                    )
    except IntegrityError:
        return _render_pattern_form(
            request,
            employee,
            mode,
            effective_from=effective_from,
            cycle_weeks=cycle_weeks,
            retroactive_confirmed=retroactive_confirmed,
            submitted_shifts=submitted_shifts,
            errors=["Someone else just saved a pattern for that date. Try again."],
        )

    if request.POST.get("notify"):
        new_shifts = {(s.week_offset, s.day): s for s in target.shifts.all()}
        changes = _diff_pattern_shifts(old_shifts, new_shifts, cycle_weeks)
        cycle_change = None
        if cycle_weeks != old_cycle:
            cycle_change = {
                "old_cycle": old_cycle,
                "new_cycle": cycle_weeks,
                "new_weeks": _new_week_details(target, old_cycle, cycle_weeks),
            }
        if changes or cycle_change:
            ok, error = notifications.send_shift_changes_email(
                employee, changes, kind="default", cycle_change=cycle_change
            )
            if not ok:
                messages.warning(request, error or "Notification not sent.")

    messages.success(
        request,
        f"Schedule saved, effective from {target.effective_from}.",
    )
    return redirect("employee_defaults", pk=employee.pk)


def _render_pattern_form(
    request,
    employee,
    mode,
    effective_from=None,
    cycle_weeks=1,
    errors=None,
    submitted_shifts=None,
    retroactive_confirmed=False,
):
    context = _pattern_form_context(
        request,
        employee,
        mode,
        effective_from=effective_from,
        cycle_weeks=cycle_weeks,
        errors=errors,
        submitted_shifts=submitted_shifts,
        retroactive_confirmed=retroactive_confirmed,
    )
    return render(request, "schedule/pattern_form.html", context)


@login_required
@permission_required("schedule.change_shift", raise_exception=True)
def schedule_change(request, pk):
    """Change schedule from a week forward."""
    today = timezone.localdate()
    employee = get_object_or_404(
        Employee.objects.filter(Q(last_day__isnull=True) | Q(last_day__gte=today)),
        pk=pk,
    )
    if request.method == "POST":
        return _handle_pattern_form_post(request, employee, mode="change")

    default_week = max(_week_start(today), _week_start(employee.start_date))
    current = _pattern_for_week(employee, default_week)
    cycle_weeks = current.cycle_weeks if current else 1
    return _render_pattern_form(
        request,
        employee,
        mode="change",
        effective_from=default_week,
        cycle_weeks=cycle_weeks,
    )


@login_required
@permission_required("schedule.change_shift", raise_exception=True)
def schedule_add(request, pk):
    """Add a new pattern at a chosen week."""
    today = timezone.localdate()
    employee = get_object_or_404(
        Employee.objects.filter(Q(last_day__isnull=True) | Q(last_day__gte=today)),
        pk=pk,
    )
    if request.method == "POST":
        return _handle_pattern_form_post(request, employee, mode="add")

    raw = request.GET.get("week", "").strip()
    effective_from = None
    if raw:
        try:
            effective_from = _week_start(date.fromisoformat(raw))
        except ValueError:
            pass

    cycle_weeks = 1
    if effective_from:
        current = _pattern_for_week(employee, effective_from)
        if current:
            cycle_weeks = current.cycle_weeks

    return _render_pattern_form(
        request,
        employee,
        mode="add",
        effective_from=effective_from,
        cycle_weeks=cycle_weeks,
    )


@login_required
@permission_required("schedule.change_shift", raise_exception=True)
def pattern_form_preview(request, pk):
    """Return just the banner + grid body for HTMX live updates."""
    today = timezone.localdate()
    employee = get_object_or_404(
        Employee.objects.filter(Q(last_day__isnull=True) | Q(last_day__gte=today)),
        pk=pk,
    )
    mode = request.GET.get("mode", "change")
    raw_effective = request.GET.get("effective_from", "").strip()
    effective_from = None
    if raw_effective:
        try:
            effective_from = _week_start(date.fromisoformat(raw_effective))
        except ValueError:
            effective_from = None

    try:
        cycle_weeks = int(request.GET.get("cycle_weeks", "1"))
    except (TypeError, ValueError):
        cycle_weeks = 1
    cycle_weeks = max(1, min(MAX_CYCLE_WEEKS, cycle_weeks))

    context = _pattern_form_context(
        request,
        employee,
        mode,
        effective_from=effective_from,
        cycle_weeks=cycle_weeks,
    )
    return render(request, "schedule/partials/_pattern_form_body.html", context)


def _render_pattern_edit_form(
    request,
    employee,
    pattern,
    is_earliest,
    cycle_weeks=None,
    errors=None,
    submitted_shifts=None,
    retroactive_confirmed=False,
):
    """Render the edit form for a single existing pattern."""
    if cycle_weeks is None:
        cycle_weeks = pattern.cycle_weeks

    context = _pattern_form_context(
        request,
        employee,
        mode="edit",
        effective_from=pattern.effective_from,
        cycle_weeks=cycle_weeks,
        errors=errors,
        submitted_shifts=submitted_shifts,
        retroactive_confirmed=retroactive_confirmed,
    )
    context["is_earliest_pattern"] = is_earliest
    context["pattern"] = pattern
    return render(request, "schedule/pattern_form.html", context)


def _handle_pattern_edit_post(request, employee, pattern, is_earliest):
    """Save an edited pattern in place.

    effective_from is locked (the picker is disabled; the hidden input
    is ignored — we read pattern.effective_from directly). No split
    branch: the pattern always exists at its own effective_from, so the
    edit-in-place case is the only case.

    Neighbor-safety: cycle_weeks can grow only within the pattern's
    existing span. If effective_to is set and the new cycle is longer
    than the span, reject. Growing past effective_to would otherwise
    silently overwrite the next pattern's territory.

    Panel index in the POST body is a calendar-week index relative to
    pattern.effective_from (0 = effective_from, 1 = +7d, ...). Save
    maps each panel to its target offset via
    (base_target_offset + cal_offset) % cycle_weeks so edits land on
    the calendar week the manager was looking at.

    Grid validation collects ALL errors before re-rendering and
    preserves every successfully-parsed cell (BUG-003), so a single
    bad cell doesn't wipe the rest of the form.
    """
    try:
        cycle_weeks = int(request.POST.get("cycle_weeks", "1"))
    except (TypeError, ValueError):
        cycle_weeks = pattern.cycle_weeks
    cycle_weeks = max(1, min(MAX_CYCLE_WEEKS, cycle_weeks))

    retroactive_confirmed = request.POST.get("retroactive_confirmed") == "1"

    if pattern.effective_to is not None:
        span_weeks = (pattern.effective_to - pattern.effective_from).days // 7
        if cycle_weeks > span_weeks:
            return _render_pattern_edit_form(
                request,
                employee,
                pattern,
                is_earliest,
                cycle_weeks=cycle_weeks,
                retroactive_confirmed=retroactive_confirmed,
                errors=[
                    f"This pattern only has {span_weeks} week(s) until "
                    f"the next pattern starts. A {cycle_weeks}-week "
                    f"cycle doesn't fit."
                ],
            )

    this_week_start = _week_start(timezone.localdate())
    is_retroactive = pattern.effective_from < this_week_start
    if is_retroactive and not retroactive_confirmed:
        return _render_pattern_edit_form(
            request,
            employee,
            pattern,
            is_earliest,
            cycle_weeks=cycle_weeks,
            retroactive_confirmed=retroactive_confirmed,
            errors=[
                "This pattern is in the past. Confirm the retroactive "
                "edit to proceed."
            ],
        )

    # Validate the grid. Collect all errors so valid cells are
    # preserved on re-render (BUG-003).
    validated_edits = {}
    submitted_shifts = {}
    errors = []
    for cal_offset in range(MAX_CYCLE_WEEKS):
        for day in DAYS:
            start_key = f"week_{cal_offset}_day_{day}_start"
            end_key = f"week_{cal_offset}_day_{day}_end"
            if start_key not in request.POST or end_key not in request.POST:
                continue
            try:
                start = _parse_time(request.POST[start_key])
                end = _parse_time(request.POST[end_key])
            except ValueError as exc:
                errors.append(
                    f"Week {WEEK_LABELS[cal_offset]} {DAY_LABELS_FULL[day]}: {exc}"
                )
                continue
            if (start is None) != (end is None):
                errors.append(
                    f"Week {WEEK_LABELS[cal_offset]} "
                    f"{DAY_LABELS_FULL[day]}: set both start and end, "
                    f"or leave both empty."
                )
                continue
            if start and end:
                submitted_shifts[(cal_offset, day)] = SimpleNamespace(
                    start_time=start, end_time=end
                )
                if end <= start:
                    errors.append(
                        f"Week {WEEK_LABELS[cal_offset]} "
                        f"{DAY_LABELS_FULL[day]}: end time must be "
                        f"after start time."
                    )
                    continue
                validated_edits[(cal_offset, day)] = (start, end)
            else:
                validated_edits[(cal_offset, day)] = None

    if errors:
        return _render_pattern_edit_form(
            request,
            employee,
            pattern,
            is_earliest,
            cycle_weeks=cycle_weeks,
            retroactive_confirmed=retroactive_confirmed,
            submitted_shifts=submitted_shifts,
            errors=errors,
        )

    # Capture the notification baseline BEFORE mutating.
    old_cycle = pattern.cycle_weeks
    old_shifts = _calendar_aligned_shifts(
        employee, pattern.effective_from, cycle_weeks
    )

    with transaction.atomic():
        if pattern.cycle_weeks != cycle_weeks:
            Shift.objects.filter(
                pattern=pattern, week_offset__gte=cycle_weeks
            ).delete()
            pattern.cycle_weeks = cycle_weeks
            pattern.save(update_fields=["cycle_weeks"])

        base_target_offset = _cycle_offset(pattern.effective_from, cycle_weeks)
        for (cal_offset, day), value in validated_edits.items():
            target_offset = (base_target_offset + cal_offset) % cycle_weeks
            if value is None:
                Shift.objects.filter(
                    pattern=pattern, week_offset=target_offset, day=day
                ).delete()
            else:
                start, end = value
                Shift.objects.update_or_create(
                    pattern=pattern,
                    week_offset=target_offset,
                    day=day,
                    defaults={"start_time": start, "end_time": end},
                )

    if request.POST.get("notify"):
        new_shifts = {(s.week_offset, s.day): s for s in pattern.shifts.all()}
        changes = _diff_pattern_shifts(old_shifts, new_shifts, cycle_weeks)
        cycle_change = None
        if cycle_weeks != old_cycle:
            cycle_change = {
                "old_cycle": old_cycle,
                "new_cycle": cycle_weeks,
                "new_weeks": _new_week_details(pattern, old_cycle, cycle_weeks),
            }
        if changes or cycle_change:
            ok, error = notifications.send_shift_changes_email(
                employee, changes, kind="default", cycle_change=cycle_change
            )
            if not ok:
                messages.warning(request, error or "Notification not sent.")

    messages.success(
        request,
        f"Pattern saved, effective from {pattern.effective_from}.",
    )
    return redirect("employee_defaults", pk=employee.pk)


@login_required
@permission_required("schedule.change_shift", raise_exception=True)
def pattern_edit(request, employee_pk, pk):
    """Edit one existing pattern in place.

    GET: render the form with shifts + cycle_weeks editable.
    POST: save in place. No split. No effective_from change.

    effective_from is locked to the pattern's existing start. The week
    picker is disabled and any POST value for it is ignored.

    Retroactive confirmation fires when the pattern's effective_from
    is in the past — editing a past pattern is destructive of written
    history.
    """
    today = timezone.localdate()
    employee = get_object_or_404(
        Employee.objects.filter(Q(last_day__isnull=True) | Q(last_day__gte=today)),
        pk=employee_pk,
    )
    pattern = get_object_or_404(ShiftPattern, pk=pk, employee=employee)

    earliest = employee.patterns.order_by("effective_from").first()
    is_earliest = earliest is not None and earliest.pk == pattern.pk

    if request.method == "POST":
        return _handle_pattern_edit_post(request, employee, pattern, is_earliest)

    return _render_pattern_edit_form(request, employee, pattern, is_earliest)


@login_required
@management_required
@permission_required("schedule.view_employee", raise_exception=True)
def employee_defaults(request, pk):
    """Render the employee reading page.

    Read-only. Identity edits and deactivation live at /details/.
    """
    today = timezone.localdate()
    employee = get_object_or_404(
        Employee.objects.filter(Q(last_day__isnull=True) | Q(last_day__gte=today)),
        pk=pk,
    )
    can_change = request.user.has_perm("schedule.change_shift")
    return _render_employee_page(
        request,
        employee,
        can_change=can_change,
    )


@login_required
@management_required
def employee_details(request, pk):
    """Edit an employee's identity, or trigger deactivation.

    Gated on `is_management` (superuser or Management group). The
    reading page stays read-only; this is the only entry point for
    identity edits.

    GET: render the form. POST: dispatch on `form=identity` to
    _handle_identity_post, which redirects back to the reading page on
    success or re-renders this page with bound errors.

    Deactivation is triggered by the Set Last Day button in the
    identity form (only rendered when the user has delete_employee).
    The modal posts to settings_deactivate_employee with
    next=employee_defaults, so the manager lands back on the reading
    page after deactivation.
    """
    today = timezone.localdate()
    employee = get_object_or_404(
        Employee.objects.filter(Q(last_day__isnull=True) | Q(last_day__gte=today)),
        pk=pk,
    )

    if request.method == "POST":
        form_type = request.POST.get("form")
        if form_type == "identity":
            return _handle_identity_post(request, employee)
        messages.error(request, "Unknown form submission.")
        return redirect("employee_details", pk=pk)

    return _render_employee_details_page(request, employee)


@login_required
@permission_required("schedule.delete_shift", raise_exception=True)
@require_POST
def delete_pattern(request, pk):
    """Delete a ShiftPattern and every shift inside it.

    The pattern must belong to an employee who's still on the roster.
    The earliest pattern for that employee is protected; edit it via
    the schedule-change page instead.

    Shift overrides within the deleted pattern's window are left in
    place. They'll be evaluated against the newly-effective pattern.
    """
    today = timezone.localdate()
    pattern = get_object_or_404(
        ShiftPattern.objects.filter(employee__last_day__isnull=True)
        | ShiftPattern.objects.filter(employee__last_day__gte=today),
        pk=pk,
    )
    employee = pattern.employee

    earliest = employee.patterns.order_by("effective_from").first()
    if earliest and earliest.pk == pattern.pk:
        messages.error(
            request,
            "Can't delete the earliest pattern. Edit it instead.",
        )
        return redirect("employee_defaults", pk=employee.pk)

    effective = pattern.effective_from
    with transaction.atomic():
        predecessor = (
            employee.patterns.filter(effective_to=pattern.effective_from)
            .exclude(pk=pattern.pk)
            .order_by("-effective_from")
            .first()
        )
        if predecessor is not None:
            predecessor.effective_to = pattern.effective_to
            predecessor.save(update_fields=["effective_to"])
        pattern.delete()
    messages.success(request, f"Deleted pattern effective from {effective}.")
    return redirect("employee_defaults", pk=employee.pk)


# ---------------------------------------------------------------------------
# 11. Views — overrides
# ---------------------------------------------------------------------------


@login_required
@require_POST
def set_override(request, employee_pk, date_iso):
    """Create, update, or clear a per-day shift override.

    The POST body's `action` field selects the operation:

    - "save": set start_time/end_time for that specific date
    - "off": mark the day off entirely
    - "reset": delete the override, falling back to the default pattern

    If `notify` is set and the cell actually changed, sends a shift
    change email to the employee — subject to eligibility rules.

    Responds two ways:

    - Plain POST → redirect back to the schedule (full page reload).
    - HTMX POST (HX-Request header) → return just the updated row so
      HTMX can swap it in place. On validation errors, retarget the
      response into the modal's `#override-error` element so the user
      sees the message without losing their input.
    """
    action = request.POST.get("action")
    is_htmx = request.headers.get("HX-Request") == "true"

    if action in ("off", "reset"):
        if not request.user.has_perm("schedule.delete_shift"):
            raise PermissionDenied
    else:
        if not request.user.has_perm("schedule.add_shift"):
            raise PermissionDenied

    today = timezone.localdate()
    employee = get_object_or_404(
        Employee.objects.filter(Q(last_day__isnull=True) | Q(last_day__gte=today)),
        pk=employee_pk,
    )
    try:
        override_date = date.fromisoformat(date_iso)
    except ValueError:
        raise Http404

    back = _home_url_for(override_date)
    old_display = _cell_display(employee, override_date)

    def _respond_error(message):
        """Return the correct shape for a validation error.

        HTMX: retarget into the modal's error slot, leave the row and
        the modal's inputs alone.
        Plain POST: flash the message and redirect, as before.
        """
        if is_htmx:
            response = HttpResponse(message)
            response["HX-Retarget"] = "#override-error"
            response["HX-Reswap"] = "innerHTML"
            return response
        messages.error(request, message)
        return redirect(back)

    def _respond_success():
        """Return the correct shape for a successful save.

        HTMX: return the updated row partial for outerHTML swap, plus
        the messages container as an out-of-band swap so any flash
        message set during the save (e.g. notification-send failures)
        surfaces without a page reload.
        Plain POST: redirect back to the schedule.
        """
        if is_htmx:
            week_start = _week_start(override_date)
            rows, _ = _build_schedule_rows(week_start, employee_pk=employee.pk)
            if rows:
                row_html = render_to_string(
                    "schedule/partials/_schedule_row.html",
                    {
                        "row": rows[0],
                        "is_management": request.user.is_superuser
                        or request.user.groups.filter(name="Management").exists(),
                    },
                    request=request,
                )
                messages_html = render_to_string(
                    "partials/_messages.html",
                    {"hx_oob": True},
                    request=request,
                )
                return HttpResponse(row_html + messages_html)
            return HttpResponse(status=204)
        return redirect(back)

    if action == "reset":
        ShiftOverride.objects.filter(employee=employee, date=override_date).delete()
    elif action == "off":
        ShiftOverride.objects.update_or_create(
            employee=employee,
            date=override_date,
            defaults={"is_off": True, "start_time": None, "end_time": None},
        )
    else:
        try:
            start = _parse_time(request.POST.get("start_time"))
            end = _parse_time(request.POST.get("end_time"))
        except ValueError as exc:
            return _respond_error(str(exc))
        if start is None or end is None:
            return _respond_error("Set both start and end time.")
        if end <= start:
            return _respond_error("End time must be after start time.")
        ShiftOverride.objects.update_or_create(
            employee=employee,
            date=override_date,
            defaults={"is_off": False, "start_time": start, "end_time": end},
        )

    if request.POST.get("notify"):
        new_display = _cell_display(employee, override_date)
        if old_display != new_display:
            ok, error = notifications.send_shift_changes_email(
                employee,
                [
                    {
                        "label": override_date.strftime("%A, %B ")
                        + _ordinal(override_date.day),
                        "old": old_display,
                        "new": new_display,
                    }
                ],
                kind="override",
            )
            # Set the message regardless of HTMX. On HTMX responses
            # the message rides back on an out-of-band swap of the
            # messages container (see _respond_success).
            if ok:
                messages.success(request, f"Notification sent to {employee.email}.")
            else:
                messages.warning(request, error or "Notification not sent.")

    return _respond_success()


@login_required
@permission_required("schedule.change_shift", raise_exception=True)
@require_POST
def set_day_override(request, date_iso):
    """Mark a whole date as Closed or Holiday, or clear that status."""
    try:
        d = date.fromisoformat(date_iso)
    except ValueError:
        raise Http404

    action = request.POST.get("action")
    back = _home_url_for(d)

    if action == "clear":
        DayOverride.objects.filter(date=d).delete()
    elif action in ("closed", "holiday"):
        DayOverride.objects.update_or_create(date=d, defaults={"status": action})

    # HTMX path: return the updated schedule table so the swap replaces
    # every affected cell for this date. A day override affects the
    # whole column plus the day header, so swapping the table is
    # simpler and cheaper to reason about than tracking N+1 out-of-
    # band swaps.
    if request.headers.get("HX-Request") == "true":
        week_start = _week_start(d)
        rows, day_headers = _build_schedule_rows(week_start)
        return render(
            request,
            "schedule/partials/_schedule_table.html",
            {
                "rows": rows,
                "day_headers": day_headers,
            },
        )

    return redirect(back)


# ---------------------------------------------------------------------------
# 12. Views — settings
# ---------------------------------------------------------------------------


@login_required
@management_required
def settings_home(request):
    """Management landing page: active employees, former employees,
    titles, and roles."""
    today = timezone.localdate()

    active_employees = (
        Employee.objects.filter(Q(last_day__isnull=True) | Q(last_day__gte=today))
        .select_related("title", "role")
        .order_by("role__display_order", "role__name", "created_at")
    )

    former_employees = (
        Employee.objects.filter(last_day__lt=today)
        .select_related("title", "role")
        .order_by("-last_day")
    )

    context = {
        "employees": active_employees,
        "former_employees": former_employees,
        "former_count": former_employees.count(),
        "titles": Title.objects.all(),
        "roles": Role.objects.all(),
        "today": today,
    }
    return render(request, "schedule/settings.html", context)


@login_required
@permission_required("schedule.add_employee", raise_exception=True)
@require_POST
def send_welcome(request, pk):
    """Send the welcome email for an employee, respecting the cooldown."""
    employee = get_object_or_404(Employee, pk=pk, is_active=True)
    ok, error = notifications.send_welcome_email(employee)
    if ok:
        messages.success(request, f"Welcome email sent to {employee.email}.")
    else:
        messages.error(request, error)
    return redirect("settings_home")


@login_required
@management_required
@require_POST
def settings_deactivate_employee(request, pk):
    """Record a last day and close the current employment period.

    - `Employee.is_active` flips False immediately, freeing the email
      for reuse.
    - The open EmploymentPeriod closes with `end_date = last_day + 1`
      (end_date is exclusive).
    - The linked User is deactivated only if the last day has already
      passed. Future departures are enforced by middleware when the
      day arrives.

    Sends a deactivation email if `notify` is set and the employee is
    still on the schedule.

    Redirect target is controlled by the POST body's `next` field:
    "employee_defaults" → the employee's reading page;
    anything else (default) → settings_home.
    """
    employee = get_object_or_404(Employee, pk=pk)

    next_target = request.POST.get("next", "settings_home")
    if next_target == "employee_defaults":
        redirect_url = reverse("employee_defaults", args=[employee.pk])
    else:
        redirect_url = reverse("settings_home")

    raw = request.POST.get("last_day", "").strip()
    if raw:
        try:
            last_day = date.fromisoformat(raw)
        except ValueError:
            messages.error(request, "Please pick a valid date.")
            return redirect(redirect_url)
    else:
        last_day = date.today()

    today = timezone.localdate()
    is_immediate = last_day < today

    with transaction.atomic():
        employee.is_active = False
        employee.last_day = last_day
        employee.save(update_fields=["is_active", "last_day"])

        current = employee.periods.filter(end_date__isnull=True).first()
        if current:
            current.end_date = last_day + timedelta(days=1)
            current.save(update_fields=["end_date"])

        if employee.user and is_immediate:
            employee.user.is_active = False
            employee.user.save(update_fields=["is_active"])

    if request.POST.get("notify"):
        ok, error = notifications.send_deactivation_email(employee)
        if ok:
            messages.success(request, f"Notification sent to {employee.email}.")
        else:
            messages.warning(request, error or "Notification not sent.")

    messages.success(request, f"{employee}'s last day will be {last_day}.")
    return redirect(redirect_url)


@login_required
@management_required
@require_POST
def settings_cancel_deactivation(request, pk):
    """Reverse a scheduled (or immediate) deactivation.

    Reopens the most recently closed period and reactivates the User.

    Redirect target is controlled by the POST body's `next` field:
    "employee_details" → the employee's details page;
    "employee_defaults" → the employee's reading page;
    anything else (default) → settings_home.
    """
    employee = get_object_or_404(Employee, pk=pk)

    next_target = request.POST.get("next", "settings_home")
    if next_target == "employee_details":
        redirect_url = reverse("employee_details", args=[employee.pk])
    elif next_target == "employee_defaults":
        redirect_url = reverse("employee_defaults", args=[employee.pk])
    else:
        redirect_url = reverse("settings_home")

    with transaction.atomic():
        current = (
            employee.periods.filter(end_date__isnull=False)
            .order_by("-end_date")
            .first()
        )
        if current:
            current.end_date = None
            current.save(update_fields=["end_date"])

        employee.is_active = True
        employee.last_day = None
        employee.save(update_fields=["is_active", "last_day"])

        if employee.user:
            employee.user.is_active = True
            employee.user.save(update_fields=["is_active"])

    messages.success(request, f"{employee}'s deactivation was cancelled.")
    return redirect(redirect_url)


@login_required
@management_required
@require_POST
def settings_reactivate_employee(request, pk):
    """Reactivate a former employee as of a chosen date.

    Opens a new EmploymentPeriod starting on that date. The employee's
    previous patterns are preserved; the schedule picks up the most
    recent pattern as of the reactivation week.
    """
    employee = get_object_or_404(Employee, pk=pk)

    raw = request.POST.get("reactivation_date", "").strip()
    if raw:
        try:
            effective = date.fromisoformat(raw)
        except ValueError:
            messages.error(request, "Please pick a valid date.")
            return redirect("settings_home")
    else:
        effective = date.today()

    with transaction.atomic():
        EmploymentPeriod.objects.create(
            employee=employee,
            start_date=effective,
            end_date=None,
        )

        employee.is_active = True
        employee.last_day = None
        employee.save(update_fields=["is_active", "last_day"])

        if employee.user:
            employee.user.is_active = True
            employee.user.save(update_fields=["is_active"])

    if request.POST.get("notify"):
        ok, error = notifications.send_welcome_email(employee)
        if ok:
            messages.success(
                request,
                f"{employee} reactivated as of {effective}. "
                f"Welcome email sent to {employee.email}.",
            )
        else:
            messages.warning(
                request,
                f"{employee} reactivated as of {effective}, "
                f"but the email failed: {error}",
            )
    else:
        messages.success(request, f"{employee} reactivated as of {effective}.")

    return redirect("settings_home")


@login_required
@management_required
@require_POST
def settings_add_title(request):
    """Create a new title. Empty names are ignored."""
    name = request.POST.get("name", "").strip()
    if name:
        Title.objects.get_or_create(name=name)
    return redirect("settings_home")


@login_required
@management_required
@require_POST
def settings_delete_title(request, pk):
    """Delete a title by ID."""
    Title.objects.filter(pk=pk).delete()
    return redirect("settings_home")


@login_required
@management_required
@require_POST
def settings_add_role(request):
    """Create a new role, placing it last in the display order."""
    name = request.POST.get("name", "").strip()
    if name:
        last = Role.objects.order_by("-display_order").first()
        next_order = (last.display_order + 10) if last else 10
        Role.objects.get_or_create(name=name, defaults={"display_order": next_order})
    return redirect("settings_home")


@login_required
@management_required
@require_POST
def settings_delete_role(request, pk):
    """Delete a role, unless any employees are still assigned to it."""
    role = get_object_or_404(Role, pk=pk)
    if role.employees.exists():
        messages.error(
            request,
            f"Can't delete {role.name} — employees are still assigned to it.",
        )
    else:
        role.delete()
    return redirect("settings_home")


@login_required
@management_required
@require_POST
def settings_move_role(request, pk, direction):
    """Swap a role's position with its neighbor and renumber everything."""
    role = get_object_or_404(Role, pk=pk)
    roles = list(Role.objects.order_by("display_order", "name"))
    idx = roles.index(role)
    swap_idx = idx - 1 if direction == "up" else idx + 1
    if swap_idx < 0 or swap_idx >= len(roles):
        return redirect("settings_home")
    roles[idx], roles[swap_idx] = roles[swap_idx], roles[idx]
    for i, r in enumerate(roles):
        r.display_order = (i + 1) * 10
        r.save(update_fields=["display_order"])
    return redirect("settings_home")


# ---------------------------------------------------------------------------
# 13. Views — print
# ---------------------------------------------------------------------------


@login_required
@management_required
def print_schedule(request):
    """Print-ready view of the schedule for one or more weeks.

    Query params:
    - `week` — anchor Monday (defaults to current week)
    - `weeks` — number of weeks to render, 1–4 (defaults to 1)
    - `color` — "color" or "bw" (defaults to "color"). Controls
      whether the print layout highlights overrides and day-level
      statuses with background colors or typography.

    Standalone template — no base.html, no Tailwind. Its own CSS
    handles screen preview and print layout. The QR code points at
    the login page so a printed sheet can be scanned to sign in.
    """
    raw_week = request.GET.get("week", "").strip()
    if raw_week:
        try:
            anchor = _week_start(date.fromisoformat(raw_week))
        except ValueError:
            anchor = _week_start(timezone.localdate())
    else:
        anchor = _week_start(timezone.localdate())

    try:
        weeks_count = int(request.GET.get("weeks", "1"))
    except (TypeError, ValueError):
        weeks_count = 1
    weeks_count = max(1, min(MAX_PRINT_WEEKS, weeks_count))

    color_mode = request.GET.get("color", "color")
    if color_mode not in ("color", "bw"):
        color_mode = "color"

    weeks = []
    for i in range(weeks_count):
        ws = anchor + timedelta(weeks=i)
        rows, day_headers = _build_schedule_rows(ws)
        weeks.append(
            {
                "week_start": ws,
                "week_title": _week_title_for(ws),
                "day_headers": day_headers,
                "rows": rows,
            }
        )

    return render(
        request,
        "schedule/print_schedule.html",
        {
            "weeks": weeks,
            "anchor": anchor,
            "anchor_iso": anchor.isoformat(),
            "selected_weeks": weeks_count,
            "week_options": list(range(1, MAX_PRINT_WEEKS + 1)),
            "range_label": _week_range_label(weeks),
            "color_mode": color_mode,
            "generated_at": timezone.now(),
        },
    )


@login_required
def qr_code(request):
    """SVG QR code pointing at the login page.

    Uses error-correction level H (30%) so the print template can
    overlay a favicon in the center without breaking scanning.
    """
    login_url = request.build_absolute_uri(reverse("login"))
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=2,
    )
    qr.add_data(login_url)
    qr.make(fit=True)
    img = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    buffer = io.BytesIO()
    img.save(buffer)
    return HttpResponse(buffer.getvalue(), content_type="image/svg+xml")
