from datetime import date, datetime, timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.db.models import Min, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import EmployeeForm
from .models import Employee, Role, Shift, ShiftOverride, Title


def management_required(view):
    """Allow superusers and members of the Management group."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if user.is_superuser or user.groups.filter(name="Management").exists():
            return view(request, *args, **kwargs)
        raise PermissionDenied

    return wrapper


DAYS = [0, 1, 2, 3, 4, 5]
DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
DAY_LABELS_FULL = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

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


def _parse_time(value):
    """Parse a user-entered time string. Returns None if empty.

    Raises ValueError if the string can't be parsed.
    """
    value = (value or "").strip()
    if not value:
        return None
    normalized = value.replace(".", "").upper()
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
    """Monday of the week containing the oldest employee's created_at, or None."""
    earliest = Employee.objects.aggregate(d=Min("created_at"))["d"]
    if earliest is None:
        return None
    return _week_start(earliest.date())


def _employees_for_week(week_start):
    """Employees who should appear in the week starting week_start (Mon–Sat).

    Includes anyone created on or before this week's Saturday, unless they
    were deactivated before this week's Monday. Per-day visibility is
    handled in _build_schedule_rows.
    """
    week_end = week_start + timedelta(days=5)
    return (
        Employee.objects.filter(created_at__date__lte=week_end)
        .filter(Q(inactivated_on__isnull=True) | Q(inactivated_on__gte=week_start))
        .select_related("title", "role")
        .prefetch_related("shifts")
        .order_by("role__display_order", "role__name", "created_at")
    )


def _build_schedule_rows(week_start):
    week_dates = [week_start + timedelta(days=d) for d in DAYS]
    employees = _employees_for_week(week_start)
    rows = []
    for emp in employees:
        defaults = {s.day: s for s in emp.shifts.all()}
        overrides = {o.date: o for o in emp.overrides.filter(date__in=week_dates)}
        cells = []
        total = timedelta()

        for day, d in zip(DAYS, week_dates):
            not_employed = emp.created_at.date() > d or (
                emp.inactivated_on is not None and emp.inactivated_on <= d
            )

            if not_employed:
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
            }
        )

    day_headers = [
        {
            "label": DAY_LABELS_FULL[i],
            "date_label": f"{d.strftime('%b')} {d.day}",
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
        "week_end": week_start + timedelta(days=5),
        "prev_week": week_start - timedelta(days=7),
        "next_week": week_start + timedelta(days=7),
        "is_current_week": week_start == current_week,
        "can_go_back": min_week is None or week_start > min_week,
    }


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
            form.save()
            return redirect("home")
    else:
        form = EmployeeForm()
    context = _home_context(_week_start(timezone.localdate()))
    context["employee_form"] = form
    context["show_add_employee_modal"] = True
    return render(request, "home.html", context)


@login_required
@permission_required("schedule.view_employee", raise_exception=True)
def employee_defaults(request, pk):
    employee = get_object_or_404(Employee, pk=pk, is_active=True)
    can_change = request.user.has_perm("schedule.change_shift")

    if request.method == "POST":
        if not can_change:
            raise PermissionDenied
        for day in DAYS:
            raw_start = request.POST.get(f"day_{day}_start", "")
            raw_end = request.POST.get(f"day_{day}_end", "")
            try:
                start = _parse_time(raw_start)
                end = _parse_time(raw_end)
            except ValueError as exc:
                messages.error(request, f"{DAY_LABELS_FULL[day]}: {exc}")
                return redirect("employee_defaults", pk=pk)
            if (start is None) != (end is None):
                messages.error(
                    request,
                    f"{DAY_LABELS_FULL[day]}: set both start and end, or leave both empty.",
                )
                return redirect("employee_defaults", pk=pk)
            if start and end:
                if end <= start:
                    messages.error(
                        request,
                        f"{DAY_LABELS_FULL[day]}: end time must be after start time.",
                    )
                    return redirect("employee_defaults", pk=pk)
                Shift.objects.update_or_create(
                    employee=employee,
                    day=day,
                    defaults={"start_time": start, "end_time": end},
                )
            else:
                Shift.objects.filter(employee=employee, day=day).delete()
        return redirect("home")

    shifts_by_day = {s.day: s for s in employee.shifts.all()}
    rows = [
        {
            "day": day,
            "label": DAY_LABELS_FULL[day],
            "shift": shifts_by_day.get(day),
        }
        for day in DAYS
    ]
    return render(
        request,
        "employee_defaults.html",
        {"employee": employee, "rows": rows, "can_change": can_change},
    )


def _home_url_for(date_):
    """Redirect to home, scrolled to the week containing date_."""
    return f"{reverse('home')}?week={_week_start(date_).isoformat()}"


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

    employee = get_object_or_404(Employee, pk=employee_pk, is_active=True)
    try:
        override_date = date.fromisoformat(date_iso)
    except ValueError:
        raise Http404

    back = _home_url_for(override_date)

    if action == "reset":
        ShiftOverride.objects.filter(employee=employee, date=override_date).delete()
    elif action == "off":
        ShiftOverride.objects.update_or_create(
            employee=employee,
            date=override_date,
            defaults={"is_off": True, "start_time": None, "end_time": None},
        )
    else:  # save
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
    return redirect(back)


def _is_management(user):
    return user.groups.filter(name="Management").exists()


@login_required
@management_required
def settings_home(request):
    today = timezone.localdate()
    employees = (
        Employee.objects.filter(
            Q(inactivated_on__isnull=True) | Q(inactivated_on__gt=today)
        )
        .select_related("title", "role")
        .order_by("role__display_order", "role__name", "created_at")
    )
    context = {
        "employees": employees,
        "titles": Title.objects.all(),
        "roles": Role.objects.all(),
        "today": today,
    }
    return render(request, "settings.html", context)


@login_required
@management_required
def settings_edit_employee(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    if request.method == "POST":
        form = EmployeeForm(request.POST, instance=employee)
        if form.is_valid():
            form.save()
            messages.success(request, f"Saved {employee}.")
            return redirect("settings_home")
    else:
        form = EmployeeForm(instance=employee)
    return render(
        request,
        "settings_edit_employee.html",
        {"form": form, "employee": employee},
    )


@login_required
@management_required
@require_POST
def settings_deactivate_employee(request, pk):
    employee = get_object_or_404(Employee, pk=pk)

    raw = request.POST.get("deactivation_date", "").strip()
    if raw:
        try:
            effective = date.fromisoformat(raw)
        except ValueError:
            messages.error(request, "Please pick a valid date.")
            return redirect("settings_home")
    else:
        effective = timezone.localdate()

    employee.is_active = False
    employee.inactivated_on = effective
    employee.save(update_fields=["is_active", "inactivated_on"])

    if employee.user:
        employee.user.is_active = False
        employee.user.save(update_fields=["is_active"])

    messages.success(
        request, f"{employee} will be off schedule from {effective} onward."
    )
    return redirect("settings_home")


@login_required
@management_required
@require_POST
def settings_cancel_deactivation(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    employee.is_active = True
    employee.inactivated_on = None
    employee.save(update_fields=["is_active", "inactivated_on"])
    if employee.user:
        employee.user.is_active = True
        employee.user.save(update_fields=["is_active"])
    messages.success(request, f"{employee}'s deactivation was cancelled.")
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
