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


def _latest_pattern(employee):
    """The most recently defined pattern for this employee."""
    return employee.patterns.order_by("-effective_from").first()


def _pattern_for_week(employee, week_start):
    """The ShiftPattern active for the week starting week_start.

    Iterates over the (prefetched) patterns relation in Python so the
    schedule render doesn't fire one query per employee. Returns None
    if no pattern covers the week.
    """
    candidates = [p for p in employee.patterns.all() if p.effective_from <= week_start]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.effective_from)


def _week_offset_for(week_start, pattern):
    """Which week of this pattern's cycle the given week falls on."""
    if pattern.cycle_weeks <= 1:
        return 0
    weeks_since_epoch = (week_start - settings.CYCLE_EPOCH).days // 7
    return weeks_since_epoch % pattern.cycle_weeks


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


def _build_schedule_rows(week_start):
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
    """
    week_dates = [week_start + timedelta(days=d) for d in DAYS]
    employees = list(_employees_for_week(week_start))
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
    return render(request, "home.html", context)


@login_required
@permission_required("schedule.add_employee", raise_exception=True)
def add_employee(request):
    """Create a new employee from the modal form on the home page.

    If a matching User account already exists (by email) and isn't
    linked to another Employee, link it automatically. Optionally send
    a welcome email when `notify` is set.

    The Employee save runs in a transaction so the post-save signals
    (which create the initial EmploymentPeriod and ShiftPattern) commit
    or roll back together with the Employee row. Without this, a
    failure in either signal could leave an Employee without a
    pattern — a state the defaults handler refuses to edit.
    """
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

            # Notification runs outside the transaction so an email
            # failure doesn't roll back a successfully created employee.
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

            return redirect("home")
    else:
        form = EmployeeForm()

    context = _home_context(_week_start(timezone.localdate()))
    context["employee_form"] = form
    context["show_add_employee_modal"] = True
    return render(request, "home.html", context)


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


def _render_employee_page(
    request, employee, identity_form=None, can_change=True, edit_pattern=None
):
    """Render the merged employee page. Used by both handlers on error.

    If `edit_pattern` is provided (from the ?pattern= query parameter),
    the defaults form is populated from that pattern's data and includes
    a hidden `target_pattern` field so the save handler edits it in
    place. Otherwise the form is populated from the latest pattern and
    the save handler picks a mode based on the submitted date.

    Context additions:

    - `patterns` — chronological (oldest first) for the bottom list.
    - `patterns_recent` — reverse chronological (newest first) for the
      strip at the top of the page.
    - `pattern_is_earliest` — whether the currently-loaded pattern is
      the earliest. Used to hide the form's delete button.
    - `can_delete` — schedule.delete_shift. Gates the pattern delete
      controls in the template, matching the boundary enforced by the
      delete_pattern view.
    - `first_time_setup` — True when the latest pattern has no shifts
      yet, so the form anchors to the pattern's own effective_from and
      the retroactive-confirm dialog is suppressed.
    """
    latest = _latest_pattern(employee)
    this_week_start = _week_start(timezone.localdate())

    form_source = edit_pattern or latest

    first_time_setup = edit_pattern is None and (
        latest is None or not latest.shifts.exists()
    )

    if edit_pattern is not None:
        default_effective_from = edit_pattern.effective_from
    elif first_time_setup and latest is not None:
        default_effective_from = latest.effective_from
    else:
        default_effective_from = this_week_start

    all_patterns = list(
        employee.patterns.order_by("effective_from").prefetch_related("shifts")
    )
    earliest_pk = all_patterns[0].pk if all_patterns else None

    patterns = [
        {
            "pattern": p,
            "weeks": _pattern_summary(p),
            "is_earliest": p.pk == earliest_pk,
        }
        for p in all_patterns
    ]

    patterns_recent = [
        {
            "pattern": p,
            "is_current": form_source is not None and p.pk == form_source.pk,
        }
        for p in reversed(all_patterns)
    ]

    pattern_is_earliest = form_source is not None and form_source.pk == earliest_pk

    return render(
        request,
        "employee_defaults.html",
        {
            "employee": employee,
            "identity_form": identity_form or EmployeeForm(instance=employee),
            "pattern": form_source,
            "patterns": patterns,
            "patterns_recent": patterns_recent,
            "weeks": _build_default_weeks(form_source) if form_source else [],
            "can_change": can_change,
            "can_delete": request.user.has_perm("schedule.delete_shift"),
            "last_day": employee.last_day,
            "default_effective_from": default_effective_from,
            "first_time_setup": first_time_setup,
            "target_pattern_pk": edit_pattern.pk if edit_pattern else "",
            "editing_pattern": edit_pattern,
            "pattern_is_earliest": pattern_is_earliest,
            "this_week_start_iso": this_week_start.isoformat(),
        },
    )


def _handle_identity_post(request, employee):
    """Save the identity form. Sync the earliest EmploymentPeriod when
    start_date changes, and slide the earliest pattern so it stays
    anchored to the Monday of the new start week.

    Moving the start date earlier slides the earliest pattern backward
    (no collision check — nothing precedes the earliest pattern).
    Moving it later slides the pattern forward, but only if it doesn't
    collide with the next pattern.

    The write phase runs in a single transaction so the Employee,
    EmploymentPeriod, and ShiftPattern rows can't drift out of sync.
    """
    old_start = employee.start_date
    form = EmployeeForm(request.POST, instance=employee)

    if not form.is_valid():
        return _render_employee_page(request, employee, identity_form=form)

    new_start = form.cleaned_data["start_date"]

    if new_start != old_start:
        earliest = employee.periods.order_by("start_date").first()
        if earliest and earliest.end_date and new_start > earliest.end_date:
            form.add_error(
                "start_date",
                f"Start date can't be after this period's end date "
                f"({earliest.end_date - timedelta(days=1):%Y-%m-%d}).",
            )
            return _render_employee_page(request, employee, identity_form=form)

    with transaction.atomic():
        form.save()

        if new_start != old_start:
            earliest = employee.periods.order_by("start_date").first()
            if earliest:
                earliest.start_date = new_start
                earliest.save(update_fields=["start_date"])

            # Keep the earliest pattern anchored to the Monday of the
            # new start week, in either direction.
            new_floor = _week_start(new_start)
            earliest_pattern = employee.patterns.order_by("effective_from").first()
            if earliest_pattern and earliest_pattern.effective_from != new_floor:
                if earliest_pattern.effective_from > new_floor:
                    # Moving earlier — extend the anchor backward. No
                    # collision possible; nothing precedes the earliest
                    # pattern.
                    earliest_pattern.effective_from = new_floor
                    earliest_pattern.save(update_fields=["effective_from"])
                else:
                    # Moving later — don't collide with the next pattern.
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


def _handle_defaults_post(request, employee):
    """Save default hour shifts as a shift pattern.

    Two entry paths:

    **Directed edit.** The form carries a `target_pattern` hidden field
    (set when the manager clicked Edit on a specific saved pattern).
    That pattern is edited in place — date, cycle length, and shifts.
    No new pattern is created. The submitted date may move the pattern,
    but only within the range allowed by the employee's start week, the
    target's neighbors, and the earliest-pattern anchoring rule.

    **Free-form save.** No `target_pattern`. The submitted effective
    date is compared against the latest pattern:

    - Same date → edit the latest pattern in place.
    - Earlier date → move the latest pattern's date back.
    - Later date → create a new pattern at the submitted date, cloning
      the latest pattern's shifts.

    In every path, the effective date must sit on or after the Monday
    of the week containing the employee's start_date. Patterns are
    Monday-aligned, so this is the earliest week a pattern can govern.

    Retroactive changes — anything effective before this week's Monday
    — require explicit confirmation via the `retroactive_confirmed`
    POST field, unless the employee is being set up for the first time
    (latest pattern has no shifts yet). The template intercepts
    submission and shows a dialog; this guard catches the case where
    JavaScript is disabled or bypassed.

    All validation runs before any database writes. The writes are
    wrapped in a transaction so a failure leaves no partial state.
    """
    latest = _latest_pattern(employee)
    if latest is None:
        messages.error(request, "No pattern exists for this employee.")
        return redirect("employee_defaults", pk=employee.pk)

    # ----- Identify the target pattern, if directed edit ---------------

    target_pk = request.POST.get("target_pattern", "").strip()
    directed_target = None
    if target_pk:
        directed_target = employee.patterns.filter(pk=target_pk).first()
        if directed_target is None:
            messages.error(
                request,
                "The pattern you were editing no longer exists.",
            )
            return redirect("employee_defaults", pk=employee.pk)

    # ----- Parse and validate inputs (no writes yet) ------------------

    raw_effective = request.POST.get("effective_from", "").strip()
    try:
        effective_from = date.fromisoformat(raw_effective)
    except ValueError, TypeError:
        messages.error(request, "Please pick a valid effective date.")
        return redirect("employee_defaults", pk=employee.pk)
    effective_from = _week_start(effective_from)

    # The pattern can't start before the employee was hired. Patterns
    # are Monday-aligned, so the floor is the Monday of the week
    # containing the employee's start date.
    start_date_floor = _week_start(employee.start_date)
    if effective_from < start_date_floor:
        messages.error(
            request,
            f"Effective date can't be before the employee's start "
            f"week ({start_date_floor}).",
        )
        return redirect("employee_defaults", pk=employee.pk)

    this_week_start = _week_start(timezone.localdate())

    # First-time setup: the latest pattern has no shifts yet, so saving
    # is defining the schedule, not rewriting it. The retroactive
    # warning would be misleading — there's no history to change.
    is_first_time = not latest.shifts.exists()

    # Retroactive guard.
    if (
        effective_from < this_week_start
        and not is_first_time
        and request.POST.get("retroactive_confirmed") != "1"
    ):
        messages.error(
            request,
            "Effective date is in the past. Confirm the retroactive change to proceed.",
        )
        return _render_employee_page(
            request,
            employee,
            can_change=True,
            edit_pattern=directed_target,
        )

    # ----- Select the target and mode ----------------------------------

    if directed_target is not None:
        target = directed_target

        # 1. No other pattern may already own the submitted date.
        if (
            employee.patterns.filter(effective_from=effective_from)
            .exclude(pk=target.pk)
            .exists()
        ):
            messages.error(
                request,
                f"Another pattern is already effective from {effective_from}.",
            )
            return redirect("employee_defaults", pk=employee.pk)

        # 2. The pattern's date must stay strictly inside the gap between
        #    its neighbors.
        prev_pattern = (
            employee.patterns.filter(effective_from__lt=target.effective_from)
            .exclude(pk=target.pk)
            .order_by("-effective_from")
            .first()
        )
        next_pattern = (
            employee.patterns.filter(effective_from__gt=target.effective_from)
            .exclude(pk=target.pk)
            .order_by("effective_from")
            .first()
        )
        if prev_pattern and effective_from <= prev_pattern.effective_from:
            messages.error(
                request,
                f"Effective date must be after the previous pattern's "
                f"start ({prev_pattern.effective_from}).",
            )
            return redirect("employee_defaults", pk=employee.pk)
        if next_pattern and effective_from >= next_pattern.effective_from:
            messages.error(
                request,
                f"Effective date must be before the next pattern's "
                f"start ({next_pattern.effective_from}).",
            )
            return redirect("employee_defaults", pk=employee.pk)

        # 3. The earliest pattern anchors the schedule from the
        #    employee's start date. It may move earlier (extending the
        #    anchor) but never forward — that would leave weeks before
        #    it with no pattern.
        earliest = employee.patterns.order_by("effective_from").first()
        if earliest and earliest.pk == target.pk:
            if effective_from > _week_start(earliest.effective_from):
                messages.error(
                    request,
                    "The earliest pattern can only move earlier, not later.",
                )
                return redirect("employee_defaults", pk=employee.pk)

        mode = "edit"
    else:
        current_start = _week_start(latest.effective_from)
        predecessor = (
            employee.patterns.filter(effective_from__lt=current_start)
            .exclude(pk=latest.pk)
            .order_by("-effective_from")
            .first()
        )
        if effective_from < current_start:
            if predecessor and effective_from <= predecessor.effective_from:
                messages.error(
                    request,
                    f"Effective date must be after the previous pattern's "
                    f"start ({predecessor.effective_from}).",
                )
                return redirect("employee_defaults", pk=employee.pk)
            target = latest
            mode = "move"
        elif effective_from == current_start:
            target = latest
            mode = "edit"
        else:
            target = latest
            mode = "create"

    try:
        cycle_weeks = int(request.POST.get("cycle_weeks", target.cycle_weeks))
    except TypeError, ValueError:
        cycle_weeks = target.cycle_weeks
    cycle_weeks = max(1, min(MAX_CYCLE_WEEKS, cycle_weeks))

    # Validate every submitted cell up front.
    validated_edits = {}
    for week_offset in range(MAX_CYCLE_WEEKS):
        for day in DAYS:
            start_key = f"week_{week_offset}_day_{day}_start"
            end_key = f"week_{week_offset}_day_{day}_end"

            if start_key not in request.POST or end_key not in request.POST:
                continue

            raw_start = request.POST[start_key]
            raw_end = request.POST[end_key]

            try:
                start = _parse_time(raw_start)
                end = _parse_time(raw_end)
            except ValueError as exc:
                messages.error(
                    request,
                    f"Week {WEEK_LABELS[week_offset]} {DAY_LABELS_FULL[day]}: {exc}",
                )
                return redirect("employee_defaults", pk=employee.pk)

            if (start is None) != (end is None):
                messages.error(
                    request,
                    f"Week {WEEK_LABELS[week_offset]} "
                    f"{DAY_LABELS_FULL[day]}: set both start and end, "
                    f"or leave both empty.",
                )
                return redirect("employee_defaults", pk=employee.pk)

            if start and end:
                if end <= start:
                    messages.error(
                        request,
                        f"Week {WEEK_LABELS[week_offset]} "
                        f"{DAY_LABELS_FULL[day]}: end time must be after "
                        f"start time.",
                    )
                    return redirect("employee_defaults", pk=employee.pk)
                validated_edits[(week_offset, day)] = (start, end)
            else:
                validated_edits[(week_offset, day)] = None

    # ----- Snapshot for the diff --------------------------------------

    old_shifts = {(s.week_offset, s.day): s for s in target.shifts.all()}
    old_cycle = target.cycle_weeks

    # ----- Apply everything in a transaction --------------------------

    try:
        with transaction.atomic():
            if mode in ("edit", "move"):
                updates = []
                if target.cycle_weeks != cycle_weeks:
                    target.cycle_weeks = cycle_weeks
                    updates.append("cycle_weeks")
                if target.effective_from != effective_from:
                    target.effective_from = effective_from
                    updates.append("effective_from")
                if updates:
                    target.save(update_fields=updates)
            else:  # create
                if employee.patterns.filter(effective_from=effective_from).exists():
                    messages.error(
                        request,
                        f"A pattern already exists effective from "
                        f"{effective_from}. Pick a different date.",
                    )
                    return redirect("employee_defaults", pk=employee.pk)

                new_pattern = ShiftPattern.objects.create(
                    employee=employee,
                    effective_from=effective_from,
                    cycle_weeks=cycle_weeks,
                )

                Shift.objects.bulk_create(
                    [
                        Shift(
                            pattern=new_pattern,
                            week_offset=s.week_offset,
                            day=s.day,
                            start_time=s.start_time,
                            end_time=s.end_time,
                        )
                        for s in target.shifts.all()
                    ]
                )
                target = new_pattern

            for (week_offset, day), value in validated_edits.items():
                if value is None:
                    Shift.objects.filter(
                        pattern=target, week_offset=week_offset, day=day
                    ).delete()
                else:
                    start, end = value
                    Shift.objects.update_or_create(
                        pattern=target,
                        week_offset=week_offset,
                        day=day,
                        defaults={"start_time": start, "end_time": end},
                    )
    except IntegrityError:
        messages.error(
            request,
            "Someone else just saved a pattern for that date. Try again.",
        )
        return redirect("employee_defaults", pk=employee.pk)

    # ----- Notify ------------------------------------------------------

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
            if ok:
                messages.success(request, f"Notification sent to {employee.email}.")
            else:
                messages.warning(request, error or "Notification not sent.")
        else:
            messages.info(request, "No changes to notify.")

    messages.success(
        request,
        f"Default hours saved, effective from {target.effective_from}.",
    )
    return redirect("employee_defaults", pk=employee.pk)


@login_required
@permission_required("schedule.view_employee", raise_exception=True)
def employee_defaults(request, pk):
    """Render or handle the merged identity + defaults page.

    POST bodies carry a `form` field that routes to the identity or
    defaults handler.

    The optional `?pattern=<uuid>` query parameter loads a specific
    saved pattern into the defaults form for editing. Without it, the
    form is populated from the latest pattern.
    """
    today = timezone.localdate()
    employee = get_object_or_404(
        Employee.objects.filter(Q(last_day__isnull=True) | Q(last_day__gte=today)),
        pk=pk,
    )
    can_change = request.user.has_perm("schedule.change_shift")

    if request.method == "POST":
        if not can_change:
            raise PermissionDenied

        form_type = request.POST.get("form")
        if form_type == "identity":
            return _handle_identity_post(request, employee)
        if form_type == "defaults":
            return _handle_defaults_post(request, employee)

        messages.error(request, "Unknown form submission.")
        return redirect("employee_defaults", pk=pk)

    # GET — optional ?pattern=<uuid> to pre-load a specific pattern
    edit_pattern = None
    pattern_param = request.GET.get("pattern", "").strip()
    if pattern_param:
        edit_pattern = employee.patterns.filter(pk=pattern_param).first()

    return _render_employee_page(
        request,
        employee,
        can_change=can_change,
        edit_pattern=edit_pattern,
    )


@login_required
@permission_required("schedule.delete_shift", raise_exception=True)
@require_POST
def delete_pattern(request, pk):
    """Delete a ShiftPattern and every shift inside it.

    The pattern must belong to an employee who's still on the roster —
    same active-employee filter used by the defaults page. The earliest
    pattern for that employee is protected; edit it via the defaults
    form instead.

    Shift overrides within the deleted pattern's window are left in
    place. They'll be evaluated against the new latest pattern once
    the deleted one is gone.

    Authority matches set_override's destructive path: delete_shift,
    not Management membership. The Settings page keeps management_required
    for its own destructive actions.
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
    """
    action = request.POST.get("action")

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
            messages.error(request, str(exc))
            return redirect(back)
        if start is None or end is None:
            messages.error(request, "Set both start and end time.")
            return redirect(back)
        if end <= start:
            messages.error(request, "End time must be after start time.")
            return redirect(back)
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
            if ok:
                messages.success(request, f"Notification sent to {employee.email}.")
            else:
                messages.warning(request, error or "Notification not sent.")

    return redirect(back)


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
    return render(request, "settings.html", context)


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
    """
    employee = get_object_or_404(Employee, pk=pk)

    raw = request.POST.get("last_day", "").strip()
    if raw:
        try:
            last_day = date.fromisoformat(raw)
        except ValueError:
            messages.error(request, "Please pick a valid date.")
            return redirect("settings_home")
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
    return redirect("settings_home")


@login_required
@management_required
@require_POST
def settings_cancel_deactivation(request, pk):
    """Reverse a scheduled (or immediate) deactivation.

    Reopens the most recently closed period and reactivates the User.
    """
    employee = get_object_or_404(Employee, pk=pk)

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
    return redirect("settings_home")


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
    except TypeError, ValueError:
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
