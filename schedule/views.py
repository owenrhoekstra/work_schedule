from datetime import date, datetime, timedelta
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db.models import Min, Q
from django.http import Http404
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
    Title,
)

# ---------------------------------------------------------------------------
# Constants
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
# Decorators
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
# Parsing and formatting helpers
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
# Week and cycle helpers
# ---------------------------------------------------------------------------


def _week_start(d):
    """Return the Monday of the week containing d."""
    return d - timedelta(days=d.weekday())


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


def _week_offset_for(week_start, employee):
    """Which week of this employee's cycle the given week falls on."""
    if employee.cycle_weeks <= 1:
        return 0
    weeks_since_epoch = (week_start - settings.CYCLE_EPOCH).days // 7
    return weeks_since_epoch % employee.cycle_weeks


def _current_or_future_employees():
    """Employees who are current or scheduled for future departure.

    Uses `last_day` — an employee is current through the end of their
    last day, so `last_day >= today` means they're still on the roster.
    """
    today = timezone.localdate()
    return Employee.objects.filter(Q(last_day__isnull=True) | Q(last_day__gte=today))


def _employees_for_week(week_start):
    """Employees with any employment period overlapping this week."""
    week_end = week_start + timedelta(days=5)
    return (
        Employee.objects.filter(periods__start_date__lte=week_end)
        .filter(Q(periods__end_date__isnull=True) | Q(periods__end_date__gt=week_start))
        .distinct()
        .select_related("title", "role")
        .prefetch_related("shifts", "periods")
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


def _home_url_for(date_):
    """Redirect to home, scrolled to the week containing date_."""
    return f"{reverse('home')}?week={_week_start(date_).isoformat()}"


# ---------------------------------------------------------------------------
# Shift display helpers
# ---------------------------------------------------------------------------


def _shift_display(shift):
    """Human-readable shift display, or None."""
    if shift is None:
        return None
    return f"{_format_time_12(shift.start_time)} – {_format_time_12(shift.end_time)}"


def _cell_display(employee, d):
    """What the schedule cell shows for this employee on this date."""
    override = employee.overrides.filter(date=d).first()
    if override:
        if override.is_off:
            return "OFF"
        return (
            f"{_format_time_12(override.start_time)} – "
            f"{_format_time_12(override.end_time)}"
        )

    week_start = _week_start(d)
    offset = _week_offset_for(week_start, employee)
    day = d.weekday()
    default = employee.shifts.filter(week_offset=offset, day=day).first()
    if default:
        return (
            f"{_format_time_12(default.start_time)} – "
            f"{_format_time_12(default.end_time)}"
        )
    return "OFF"


def _diff_default_changes(employee, old_shifts):
    """List change dicts for default shifts that changed.

    `old_shifts` is a dict keyed by (week_offset, day). Compares against
    the current DB state. Only offsets within the active cycle_weeks.
    """
    new_shifts = {(s.week_offset, s.day): s for s in employee.shifts.all()}
    cycle = employee.cycle_weeks

    changes = []
    keys = sorted(set(old_shifts) | set(new_shifts), key=lambda k: (k[0], k[1]))
    for key in keys:
        week_offset, day = key
        if week_offset >= cycle:
            continue

        old = old_shifts.get(key)
        new = new_shifts.get(key)
        old_display = _shift_display(old) or "OFF"
        new_display = _shift_display(new) or "OFF"

        if old_display == new_display:
            continue

        if cycle == 1:
            label = DAY_LABELS_FULL[day]
        else:
            label = f"Week {WEEK_LABELS[week_offset]} {DAY_LABELS_FULL[day]}"

        changes.append({"label": label, "old": old_display, "new": new_display})

    return changes


def _new_week_details(employee, old_cycle, new_cycle):
    """Build rows for weeks that become active when the cycle increases.

    Returns an empty list when the cycle didn't grow.
    """
    if new_cycle <= old_cycle:
        return []
    shifts_by_key = {(s.week_offset, s.day): s for s in employee.shifts.all()}
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


# ---------------------------------------------------------------------------
# Schedule building
# ---------------------------------------------------------------------------


def _build_schedule_rows(week_start):
    week_dates = [week_start + timedelta(days=d) for d in DAYS]
    employees = _employees_for_week(week_start)
    day_overrides = {o.date: o for o in DayOverride.objects.filter(date__in=week_dates)}
    rows = []
    for emp in employees:
        offset = _week_offset_for(week_start, emp)
        defaults = {s.day: s for s in emp.shifts.all() if s.week_offset == offset}
        overrides = {o.date: o for o in emp.overrides.filter(date__in=week_dates)}
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
                }
            )

        rows.append(
            {
                "employee": emp,
                "cells": cells,
                "total_hours": _format_duration(total),
                "cycle_label": (WEEK_LABELS[offset] if emp.cycle_weeks > 1 else None),
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

    day_with_ordinal = _ordinal(week_start.day)
    if week_start.year == current_week.year:
        week_title = f"Week of {week_start.strftime('%B')} {day_with_ordinal}"
    else:
        week_title = (
            f"Week of {week_start.strftime('%B')} {day_with_ordinal}, {week_start.year}"
        )

    return {
        "rows": rows,
        "day_headers": day_headers,
        "week_start": week_start,
        "week_title": week_title,
        "prev_week": week_start - timedelta(days=7),
        "next_week": week_start + timedelta(days=7),
        "is_current_week": week_start == current_week,
        "can_go_back": min_week is None or week_start > min_week,
    }


# ---------------------------------------------------------------------------
# Views — schedule
# ---------------------------------------------------------------------------


@login_required
@permission_required("schedule.view_shift", raise_exception=True)
def home(request):
    week_start = _parse_week_param(request) or _week_start(timezone.localdate())
    context = _home_context(week_start)
    if request.user.has_perm("schedule.add_employee"):
        context["employee_form"] = EmployeeForm()
    return render(request, "home.html", context)


@login_required
@permission_required("schedule.add_employee", raise_exception=True)
def add_employee(request):
    if request.method == "POST":
        form = EmployeeForm(request.POST)
        if form.is_valid():
            employee = form.save(commit=False)

            matching_user = User.objects.filter(email__iexact=employee.email).first()
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

            return redirect("home")
    else:
        form = EmployeeForm()

    context = _home_context(_week_start(timezone.localdate()))
    context["employee_form"] = form
    context["show_add_employee_modal"] = True
    return render(request, "home.html", context)


# ---------------------------------------------------------------------------
# Employee page — merged identity + defaults
# ---------------------------------------------------------------------------


def _build_default_weeks(employee):
    """Assemble the week/row structure for the defaults editor."""
    shifts_by_key = {(s.week_offset, s.day): s for s in employee.shifts.all()}
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


def _render_employee_page(request, employee, identity_form=None, can_change=True):
    """Render the merged employee page. Used by both handlers on error."""
    return render(
        request,
        "employee_defaults.html",
        {
            "employee": employee,
            "identity_form": identity_form or EmployeeForm(instance=employee),
            "weeks": _build_default_weeks(employee),
            "can_change": can_change,
            "last_day": employee.last_day,
        },
    )


def _handle_identity_post(request, employee):
    """Save the identity form. Sync EmploymentPeriod when start_date changes."""
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

    form.save()

    if new_start != old_start:
        earliest = employee.periods.order_by("start_date").first()
        if earliest:
            earliest.start_date = new_start
            earliest.save(update_fields=["start_date"])

    messages.success(request, f"Saved {employee}.")
    return redirect("employee_defaults", pk=employee.pk)


def _handle_defaults_post(request, employee):
    """Save default hour shifts. Handles cycle changes and notification."""
    old_shifts = {(s.week_offset, s.day): s for s in employee.shifts.all()}
    old_cycle = employee.cycle_weeks

    try:
        cycle_weeks = int(request.POST.get("cycle_weeks", employee.cycle_weeks))
    except TypeError, ValueError:
        cycle_weeks = employee.cycle_weeks
    cycle_weeks = max(1, min(MAX_CYCLE_WEEKS, cycle_weeks))

    if cycle_weeks != employee.cycle_weeks:
        employee.cycle_weeks = cycle_weeks
        employee.save(update_fields=["cycle_weeks"])

    for week_offset in range(MAX_CYCLE_WEEKS):
        for day in DAYS:
            start_key = f"week_{week_offset}_day_{day}_start"
            end_key = f"week_{week_offset}_day_{day}_end"

            if start_key not in request.POST and end_key not in request.POST:
                continue

            raw_start = request.POST.get(start_key, "")
            raw_end = request.POST.get(end_key, "")

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
                Shift.objects.update_or_create(
                    employee=employee,
                    week_offset=week_offset,
                    day=day,
                    defaults={"start_time": start, "end_time": end},
                )
            else:
                Shift.objects.filter(
                    employee=employee,
                    week_offset=week_offset,
                    day=day,
                ).delete()

    if request.POST.get("notify"):
        changes = _diff_default_changes(employee, old_shifts)
        cycle_change = None
        if cycle_weeks != old_cycle:
            cycle_change = {
                "old_cycle": old_cycle,
                "new_cycle": cycle_weeks,
                "new_weeks": _new_week_details(employee, old_cycle, cycle_weeks),
            }

        if changes or cycle_change:
            notifications.send_shift_changes_email(
                employee, changes, kind="default", cycle_change=cycle_change
            )
            messages.success(request, f"Notification sent to {employee.email}.")
        else:
            messages.info(request, "No changes to notify.")

    messages.success(request, "Default hours saved.")
    return redirect("employee_defaults", pk=employee.pk)


@login_required
@permission_required("schedule.view_employee", raise_exception=True)
def employee_defaults(request, pk):
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

    return _render_employee_page(request, employee, can_change=can_change)


# ---------------------------------------------------------------------------
# Overrides
# ---------------------------------------------------------------------------


@login_required
@require_POST
def set_override(request, employee_pk, date_iso):
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
            notifications.send_shift_changes_email(
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
            messages.success(request, f"Notification sent to {employee.email}.")

    return redirect(back)


@login_required
@permission_required("schedule.change_shift", raise_exception=True)
@require_POST
def set_day_override(request, date_iso):
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
# Views — settings
# ---------------------------------------------------------------------------


@login_required
@management_required
def settings_home(request):
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
    """Mark a last day. Internally, "off" begins the following day."""
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

    # Employee row: mark inactive immediately (frees the email for reuse)
    # and record the last_day the manager entered.
    employee.is_active = False
    employee.last_day = last_day
    employee.save(update_fields=["is_active", "last_day"])

    # Employment period: end_date is exclusive, so it's the day after.
    current = employee.periods.filter(end_date__isnull=True).first()
    if current:
        current.end_date = last_day + timedelta(days=1)
        current.save(update_fields=["end_date"])

    # User account: only flip off if the departure already happened.
    # Future deactivations are enforced by middleware when the day arrives.
    if employee.user and is_immediate:
        employee.user.is_active = False
        employee.user.save(update_fields=["is_active"])

    if request.POST.get("notify"):
        notifications.send_deactivation_email(employee)

    messages.success(request, f"{employee}'s last day will be {last_day}.")
    return redirect("settings_home")


@login_required
@management_required
@require_POST
def settings_cancel_deactivation(request, pk):
    employee = get_object_or_404(Employee, pk=pk)

    current = (
        employee.periods.filter(end_date__isnull=False).order_by("-end_date").first()
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
    name = request.POST.get("name", "").strip()
    if name:
        Title.objects.get_or_create(name=name)
    return redirect("settings_home")


@login_required
@management_required
@require_POST
def settings_delete_title(request, pk):
    Title.objects.filter(pk=pk).delete()
    return redirect("settings_home")


@login_required
@management_required
@require_POST
def settings_add_role(request):
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
