"""Structured-data selectors for the schedule app.

JSON-ready counterparts to the Django HTML home view's row building.
Consumed by /api/v1/schedule/week/ and by /me/ (for available_scopes).

`_build_schedule_rows` in views.py stays as the Django-template
adapter until the HTML home is retired; both call the same pure
helpers (`_employees_for_week`, `_pattern_for_week`, `_week_offset_for`,
`_employed_dates`), only the output shape differs. Duplication is
temporary and intentional — see SESSIONS.md Commit 3 entry.
"""

from datetime import timedelta

from django.utils import timezone

from .models import (
    DayOverride,
    EmployeeTeam,
    ShiftOverride,
    TeamMembership,
)
from .scheduling import (
    DAY_LABELS,
    DAY_LABELS_FULL,
    DAYS,
    WEEK_LABELS,
    _earliest_week,
    _employed_dates,
    _employees_for_week,
    _pattern_for_week,
    _week_offset_for,
    _week_start,
    _week_title_for,
)

# ---------------------------------------------------------------------------
# Scope resolution
# ---------------------------------------------------------------------------


def _employee_for(user, company):
    if not user.is_authenticated:
        return None
    return user.employees.filter(company=company).first()


def _is_employed(employee):
    if employee is None:
        return False
    today = timezone.localdate()
    return employee.last_day is None or employee.last_day >= today


def _viewer_team_ids(viewer, employee, company):
    """Teams the viewer can see as a team member or admin.

    Two sources union:
    - EmployeeTeam (member path): teams the viewer is scheduled on,
      where the team has allow_member_view_all=True AND the employee's
      own show_team_schedules is True. The per-employee opt-out gates
      the member path even when the team permits viewing.
    - TeamMembership (admin path): teams the viewer admins, regardless
      of allow_member_view_all or show_team_schedules — admins always
      see the teams they administer.
    """
    ids = set()
    if employee is not None and employee.show_team_schedules:
        for et in EmployeeTeam.objects.filter(
            employee=employee,
            valid_to__isnull=True,
            team__company=company,
            team__allow_member_view_all=True,
        ):
            ids.add(et.team_id)
    if viewer.is_authenticated:
        for tm in TeamMembership.objects.filter(
            user=viewer,
            role="admin",
            valid_to__isnull=True,
            team__company=company,
        ):
            ids.add(tm.team_id)
    return ids


def available_scopes_for(company, user):
    """Which scopes the given user can view at this company.

    Returns a subset of ["me", "team", "company"], in that order.

    - me: the user has an Employee row at this company AND is employed.
    - team: the user is on a team whose allow_member_view_all is True
      (and their own show_team_schedules is True), OR the user is a
      team admin of any team in this company.
    - company: the user is a company admin, OR the company's
      allow_member_view_all is True AND the user is employed.
    """
    from work_schedule.auth import is_company_admin

    if company is None or not user.is_authenticated:
        return []

    employee = _employee_for(user, company)
    employed = _is_employed(employee)

    scopes = []
    if employed:
        scopes.append("me")

    has_member_team = False
    if employed and employee.show_team_schedules:
        has_member_team = EmployeeTeam.objects.filter(
            employee=employee,
            valid_to__isnull=True,
            team__company=company,
            team__allow_member_view_all=True,
        ).exists()
    has_admin_team = TeamMembership.objects.filter(
        user=user,
        role="admin",
        valid_to__isnull=True,
        team__company=company,
    ).exists()
    if has_member_team or has_admin_team:
        scopes.append("team")

    if is_company_admin(user, company):
        scopes.append("company")
    elif employed and company.allow_member_view_all:
        scopes.append("company")

    return scopes


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------


def _build_week_ref(company, week_start):
    current = _week_start(timezone.localdate())
    min_week = _earliest_week(company)
    return {
        "start": week_start.isoformat(),
        "title": _week_title_for(week_start),
        "prev": (week_start - timedelta(days=7)).isoformat(),
        "next": (week_start + timedelta(days=7)).isoformat(),
        "is_current": week_start == current,
        "can_go_back": min_week is None or week_start > min_week,
    }


def _build_day_headers(week_start, day_overrides):
    week_dates = [week_start + timedelta(days=i) for i in DAYS]
    headers = []
    for i, d in enumerate(week_dates):
        override = day_overrides.get(d)
        headers.append(
            {
                "date": d.isoformat(),
                "weekday": i,
                "short_label": DAY_LABELS[i],
                "long_label": DAY_LABELS_FULL[i],
                "date_label": f"{d.strftime('%b')} {d.day}",
                "override_status": override.status if override else None,
            }
        )
    return headers


def _minutes_between(start_str, end_str):
    sh, sm = map(int, start_str.split(":"))
    eh, em = map(int, end_str.split(":"))
    return (eh * 60 + em) - (sh * 60 + sm)


def _build_cell(day, d, day_override, employed, defaults, overrides):
    base = {"date": d.isoformat(), "weekday": day}
    if day_override:
        return {
            **base,
            "kind": "day_override",
            "start": None,
            "end": None,
            "has_override": False,
            "is_employed": False,
        }
    if d not in employed:
        return {
            **base,
            "kind": "not_employed",
            "start": None,
            "end": None,
            "has_override": False,
            "is_employed": False,
        }
    default_shift = defaults.get(day)
    override = overrides.get(d)
    if override and override.is_off:
        return {
            **base,
            "kind": "off_override",
            "start": None,
            "end": None,
            "has_override": True,
            "is_employed": True,
        }
    if override:
        return {
            **base,
            "kind": "override",
            "start": override.start_time.strftime("%H:%M"),
            "end": override.end_time.strftime("%H:%M"),
            "has_override": True,
            "is_employed": True,
        }
    if default_shift:
        return {
            **base,
            "kind": "default",
            "start": default_shift.start_time.strftime("%H:%M"),
            "end": default_shift.end_time.strftime("%H:%M"),
            "has_override": False,
            "is_employed": True,
        }
    return {
        **base,
        "kind": "none",
        "start": None,
        "end": None,
        "has_override": False,
        "is_employed": True,
    }


def _employee_week_row(employee, week_start, overrides_by_employee, day_overrides):
    week_dates = [week_start + timedelta(days=d) for d in DAYS]
    pattern = _pattern_for_week(employee, week_start)
    offset = _week_offset_for(week_start, pattern) if pattern else 0
    defaults = (
        {s.day: s for s in pattern.shifts.all() if s.week_offset == offset}
        if pattern
        else {}
    )
    overrides = overrides_by_employee.get(employee.id, {})
    employed = _employed_dates(employee, week_dates)

    cells = []
    total_minutes = 0
    for day, d in zip(DAYS, week_dates):
        cell = _build_cell(day, d, day_overrides.get(d), employed, defaults, overrides)
        cells.append(cell)
        if cell["start"] and cell["end"]:
            total_minutes += _minutes_between(cell["start"], cell["end"])

    cycle = None
    if pattern is not None and pattern.cycle_weeks > 1:
        cycle = {
            "label": WEEK_LABELS[offset],
            "offset": offset,
            "total": pattern.cycle_weeks,
        }

    return {
        "id": str(employee.id),
        "first_name": employee.first_name,
        "last_name": employee.last_name,
        "display_name": f"{employee.first_name} {employee.last_name}".strip(),
        "role_id": str(employee.role_id) if employee.role_id else None,
        "role_name": employee.role.name if employee.role_id else None,
        "last_day": employee.last_day.isoformat() if employee.last_day else None,
        "cycle": cycle,
        "cells": cells,
        "total_minutes": total_minutes,
    }


def _viewer_can(viewer, company):
    from work_schedule.auth import is_company_admin

    if not is_company_admin(viewer, company):
        return {
            "set_override": False,
            "set_day_override": False,
            "add_employee": False,
            "print": False,
        }
    return {
        "set_override": (
            viewer.has_perm("schedule.add_shift")
            or viewer.has_perm("schedule.delete_shift")
        ),
        "set_day_override": viewer.has_perm("schedule.change_shift"),
        "add_employee": viewer.has_perm("schedule.add_employee"),
        "print": True,
    }


# ---------------------------------------------------------------------------
# Scoped employee queryset
# ---------------------------------------------------------------------------


def _scoped_employees(company, week_start, scope, viewer, employee):
    base = _employees_for_week(week_start, company)

    if scope == "me":
        if employee is None:
            return base.none()
        return base.filter(pk=employee.pk)

    if scope == "company":
        return base

    if scope == "team":
        team_ids = _viewer_team_ids(viewer, employee, company)
        if not team_ids:
            return base.none()
        return base.filter(
            team_links__team_id__in=team_ids,
            team_links__valid_to__isnull=True,
        ).distinct()

    raise ValueError(f"Unknown scope: {scope!r}")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def week_schedule_for_scope(company, week_start, scope, viewer):
    """Build the structured schedule payload for one week/scope.

    Caller is responsible for checking `scope in available_scopes_for(...)`
    first — this function assumes the viewer is authorized for the scope
    and will return an empty roster rather than raising on empty.
    """
    employee = _employee_for(viewer, company)

    employees = list(_scoped_employees(company, week_start, scope, viewer, employee))
    week_dates = [week_start + timedelta(days=d) for d in DAYS]

    day_overrides = {
        o.date: o
        for o in DayOverride.objects.filter(date__in=week_dates, company=company)
    }

    overrides_by_employee = {}
    if employees:
        for override in ShiftOverride.objects.filter(
            employee__in=employees,
            employee__company=company,
            date__in=week_dates,
        ):
            overrides_by_employee.setdefault(override.employee_id, {})[
                override.date
            ] = override

    return {
        "week": _build_week_ref(company, week_start),
        "days": _build_day_headers(week_start, day_overrides),
        "scope": scope,
        "available_scopes": available_scopes_for(company, viewer),
        "employees": [
            _employee_week_row(e, week_start, overrides_by_employee, day_overrides)
            for e in employees
        ],
        "viewer_can": _viewer_can(viewer, company),
    }
