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

from django.db.models import Q
from django.utils import timezone

from .models import (
    DayOverride,
    Employee,
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
    _last_week_of,
    _pattern_for_week,
    _pattern_summary,
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


def viewable_team_ids(user, company):
    """Team IDs the user can view as team scope.

    Public wrapper around _viewer_team_ids that resolves the user's
    Employee row first. Used by accounts.api (teams/select, /me/
    filtering) and by schedule.api.week (defensive: an unviewable
    session team returns empty rather than leaking).

    Returns an empty set when the user has no Employee and no
    admin-role TeamMembership at this company.
    """
    employee = _employee_for(user, company)
    return _viewer_team_ids(user, employee, company)


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

    if is_company_admin(user, company) or employed and company.allow_member_view_all:
        scopes.append("company")

    return scopes


# ---------------------------------------------------------------------------
# Employee drawer: current pattern + who may open whom
# ---------------------------------------------------------------------------


def current_pattern_context(employee):
    """Current-week pattern pieces. Shared by the HTML defaults page
    and the employee drawer API so the two can't drift."""
    this_week_start = _week_start(timezone.localdate())
    current = _pattern_for_week(employee, this_week_start)

    current_weeks = _pattern_summary(current) if current else []
    current_cycle_label = None
    if current is not None and current.cycle_weeks > 1:
        offset = _week_offset_for(this_week_start, current)
        current_cycle_label = WEEK_LABELS[offset]

    current_last_week = _last_week_of(current)
    return {
        "current_pattern": current,
        "current_weeks": current_weeks,
        "current_last_week": current_last_week,
        "current_last_week_end": (
            current_last_week + timedelta(days=6) if current_last_week else None
        ),
        "current_cycle_label": current_cycle_label,
    }


def managed_team_ids(user, company):
    """Teams the user administers at this company."""
    if not user.is_authenticated:
        return set()
    return set(
        TeamMembership.objects.filter(
            user=user,
            role="admin",
            valid_to__isnull=True,
            team__company=company,
        ).values_list("team_id", flat=True)
    )


def employees_visible_to(viewer, company):
    """Every employee the viewer may open, across all of their scopes.

    Same rules as week_schedule_for_scope (me / team / company), minus
    the week window: the drawer must open for anyone the table can show
    in any week. Anyone not in this set is indistinguishable from a
    nonexistent ID (callers 404).
    """
    base = Employee.objects.filter(company=company)
    scopes = available_scopes_for(company, viewer)
    if "company" in scopes:
        return base

    employee = _employee_for(viewer, company)
    q = Q()
    if "me" in scopes and employee is not None:
        q |= Q(pk=employee.pk)
    if "team" in scopes:
        team_ids = _viewer_team_ids(viewer, employee, company)
        if team_ids:
            q |= Q(team_links__team_id__in=team_ids, team_links__valid_to__isnull=True)
    if not q:
        return base.none()
    return base.filter(q).distinct()


def is_team_admin_of_employee(viewer, company, employee):
    """True if the viewer administers a team this employee is currently on."""
    team_ids = managed_team_ids(viewer, company)
    if not team_ids:
        return False
    return EmployeeTeam.objects.filter(
        employee=employee, valid_to__isnull=True, team_id__in=team_ids
    ).exists()


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

    default_shift = defaults.get(day)
    default_start = (
        default_shift.start_time.strftime("%H:%M") if default_shift else None
    )
    default_end = default_shift.end_time.strftime("%H:%M") if default_shift else None

    if day_override:
        return {
            **base,
            "kind": "day_override",
            "start": None,
            "end": None,
            "has_override": False,
            "is_employed": False,
            "default_start": default_start,
            "default_end": default_end,
        }
    if d not in employed:
        return {
            **base,
            "kind": "not_employed",
            "start": None,
            "end": None,
            "has_override": False,
            "is_employed": False,
            "default_start": default_start,
            "default_end": default_end,
        }
    override = overrides.get(d)
    if override and override.is_off:
        return {
            **base,
            "kind": "off_override",
            "start": None,
            "end": None,
            "has_override": True,
            "is_employed": True,
            "default_start": default_start,
            "default_end": default_end,
        }
    if override:
        return {
            **base,
            "kind": "override",
            "start": override.start_time.strftime("%H:%M"),
            "end": override.end_time.strftime("%H:%M"),
            "has_override": True,
            "is_employed": True,
            "default_start": default_start,
            "default_end": default_end,
        }
    if default_shift:
        return {
            **base,
            "kind": "default",
            "start": default_start,
            "end": default_end,
            "has_override": False,
            "is_employed": True,
            "default_start": default_start,
            "default_end": default_end,
        }
    return {
        **base,
        "kind": "none",
        "start": None,
        "end": None,
        "has_override": False,
        "is_employed": True,
        "default_start": None,
        "default_end": None,
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
            "can_add_shift": False,
            "can_delete_shift": False,
            "change_employee_day_override": False,
            "change_day_override": False,
            "add_employee": False,
            "print": False,
        }
    return {
        "can_add_shift": viewer.has_perm("schedule.add_shift"),
        "can_delete_shift": viewer.has_perm("schedule.delete_shift"),
        "change_employee_day_override": viewer.has_perm("schedule.change_shift"),
        "change_day_override": viewer.has_perm("schedule.change_dayoverride"),
        "add_employee": viewer.has_perm("schedule.add_employee"),
        "print": True,
    }


# ---------------------------------------------------------------------------
# Scoped employee queryset
# ---------------------------------------------------------------------------


def _scoped_employees(company, week_start, scope, viewer, employee, team=None):
    base = _employees_for_week(week_start, company)

    if scope == "me":
        if employee is None:
            return base.none()
        return base.filter(pk=employee.pk)

    if scope == "company":
        return base

    if scope == "team":
        viewable = _viewer_team_ids(viewer, employee, company)
        if team is not None:
            # Defensive: session team that isn't viewable (stale, or
            # viewability lost after session write) yields empty.
            if team.id not in viewable:
                return base.none()
            target = {team.id}
        else:
            target = viewable
        if not target:
            return base.none()
        return base.filter(
            team_links__team_id__in=target,
            team_links__valid_to__isnull=True,
        ).distinct()

    raise ValueError(f"Unknown scope: {scope!r}")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def week_schedule_for_scope(company, week_start, scope, viewer, team=None):
    """..."""
    employee = _employee_for(viewer, company)

    employees = list(
        _scoped_employees(company, week_start, scope, viewer, employee, team)
    )
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


def week_row_for(company, employee, week_start):
    """Build a single WeekEmployee row for one employee/week.

    Used by the override mutation endpoint to return the updated row
    in the same shape as /week/'s employees[] — client can replace its
    cached copy without a second fetch.
    """
    week_dates = [week_start + timedelta(days=d) for d in DAYS]
    day_overrides = {
        o.date: o
        for o in DayOverride.objects.filter(date__in=week_dates, company=company)
    }
    overrides_by_employee = {}
    for override in ShiftOverride.objects.filter(
        employee=employee,
        employee__company=company,
        date__in=week_dates,
    ):
        overrides_by_employee.setdefault(override.employee_id, {})[override.date] = (
            override
        )
    return _employee_week_row(
        employee, week_start, overrides_by_employee, day_overrides
    )
