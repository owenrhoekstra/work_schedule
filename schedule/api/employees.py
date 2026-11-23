"""Employee drawer endpoints: detail, quick-setting flags, welcome email."""

from uuid import UUID

from ninja import Router
from ninja.errors import HttpError

from schedule.employee_flags import FLAGS, FLAGS_BY_KEY, FlagDef
from schedule.models import Employee
from schedule.notifications import WELCOME_COOLDOWN_MSG, send_welcome_email
from schedule.selectors import (
    current_pattern_context,
    employees_visible_to,
    is_team_admin_of_employee,
)
from work_schedule.api.auth import session_auth

from .authz import authorize
from .schemas import EmployeeDetailOut, EmployeeFlagOut, FlagIn

router = Router(tags=["employees"], auth=session_auth)


def _get_employee(request, company, employee_id):
    """Scoped lookup. Out-of-scope and nonexistent are both 404, so a
    team admin can't probe for employees outside their teams."""
    try:
        return (
            employees_visible_to(request.user, company)
            .select_related("role")
            .get(pk=employee_id)
        )
    except Employee.DoesNotExist:
        raise HttpError(404, "Employee not found.")


def _access(request, company, employee):
    """'company', 'team' or None: how this viewer may manage this employee."""
    if getattr(request, "is_company_admin", False):
        return "company"
    if is_team_admin_of_employee(request.user, company, employee):
        return "team"
    return None


def _can_edit_flag(request, flag: FlagDef, access) -> bool:
    if access is None:
        return False
    if access == "team" and not flag.team_admin_can_edit:
        return False
    return flag.edit_perm is None or request.user.has_perm(flag.edit_perm)


def _flag_out(request, flag: FlagDef, employee, access) -> dict:
    return {
        "key": flag.key,
        "label": flag.label,
        "description": flag.description,
        "value": flag.get(employee),
        "can_edit": _can_edit_flag(request, flag, access),
    }


def _get(obj, name):
    return obj[name] if isinstance(obj, dict) else getattr(obj, name)


def _hhmm(t):
    return t.strftime("%H:%M") if t else None


def _summarize_pattern(ctx: dict) -> dict | None:
    pattern = ctx.get("current_pattern")
    if pattern is None:
        return None
    weeks = []
    for w in ctx["current_weeks"]:
        days = []
        for r in _get(w, "rows"):
            shift = _get(r, "shift")
            days.append(
                {
                    "label": _get(r, "label"),
                    "start": _hhmm(shift.start_time) if shift else None,
                    "end": _hhmm(shift.end_time) if shift else None,
                }
            )
        weeks.append({"label": _get(w, "label"), "days": days})
    return {
        "effective_from": pattern.effective_from,
        "through": ctx.get("current_last_week_end"),
        "cycle_weeks": pattern.cycle_weeks,
        "current_cycle_label": ctx.get("current_cycle_label") or None,
        "weeks": weeks,
    }


@router.get("/{employee_id}/", response=EmployeeDetailOut)
def employee_detail(request, employee_id: UUID):
    """Drawer payload for anyone the viewer can see in some scope.

    Managers (company admin, or admin of one of the employee's teams)
    additionally get email and the flag list. Plain viewers get the
    schedule only.
    """
    company = authorize(request, "schedule.view_shift", admin=False)
    employee = _get_employee(request, company, employee_id)
    access = _access(request, company, employee)

    return {
        "id": employee.pk,
        "email": employee.email if access else None,
        "start_date": employee.start_date,
        "last_day": employee.last_day,
        "flags": [_flag_out(request, f, employee, access) for f in FLAGS]
        if access
        else [],
        "pattern": _summarize_pattern(current_pattern_context(employee)),
        "can": {
            "send_welcome": access == "company"
            and request.user.has_perm("schedule.add_employee"),
        },
    }


@router.post("/{employee_id}/flags/", response=EmployeeFlagOut)
def set_flag(request, employee_id: UUID, payload: FlagIn):
    flag = FLAGS_BY_KEY.get(payload.key)
    company = authorize(request, "schedule.view_shift", admin=False)
    employee = _get_employee(request, company, employee_id)
    access = _access(request, company, employee)

    if flag is None:
        raise HttpError(422, "Unknown setting.")
    if not _can_edit_flag(request, flag, access):
        raise HttpError(403, "Forbidden.")

    flag.set(employee, payload.value)
    return _flag_out(request, flag, employee, access)


@router.post("/{employee_id}/welcome/")
def send_welcome(request, employee_id: UUID):
    company = authorize(request, "schedule.add_employee")  # company admin only
    employee = _get_employee(request, company, employee_id)
    if employee.last_day:
        raise HttpError(422, "Employee has a last day set.")

    ok, error = send_welcome_email(employee)
    if not ok:
        raise HttpError(429 if error == WELCOME_COOLDOWN_MSG else 502, error)
    return {"sent": True}
