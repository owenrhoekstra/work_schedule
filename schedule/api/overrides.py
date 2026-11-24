"""Override mutation endpoints (per-employee shifts and whole-day status)."""

from datetime import date
from uuid import UUID

from django.db.models import Q
from django.utils import timezone
from ninja import Router
from ninja.errors import HttpError

from schedule.models import DayOverride, Employee
from schedule.scheduling import _employed_dates, _week_start
from schedule.selectors import DAY_OVERRIDE_PERMS, week_row_for
from schedule.services import OverrideError, apply_override
from work_schedule.api.auth import session_auth
from work_schedule.api.permissions import HasPerm

from .schemas import (
    DayOverrideIn,
    DayOverrideOut,
    OverrideRequest,
    OverrideResponse,
)

router = Router(tags=["overrides"], auth=session_auth)


# Route order matters: Ninja registers patterns as declared and matches
# {employee_id} as a plain string before validating it as a UUID. If
# this route moves below override(), "/days/..." would hit that one and
# fail with a 422. Keep this one first.
@router.post(
    "/days/{target_date}/",
    auth=HasPerm(*DAY_OVERRIDE_PERMS),
    response=DayOverrideOut,
)
def set_day_override(request, target_date: date, payload: DayOverrideIn):
    """Mark a whole date as Closed or Holiday, or clear that status.

    Authz: HasPerm(*DAY_OVERRIDE_PERMS) = company admin +
    change_dayoverride + view_shift, matching the HTML set_day_override
    view's decorator stack. Returns the resulting status; the client
    invalidates its week query to pick up the new column state.
    """
    company = request.company

    # team=None limits this to company-wide rows, matching override().
    # Team-scoped DayOverrides are reserved for the teams UI and must
    # not be cleared or clobbered from here.
    scope = {"date": target_date, "company": company, "team": None}

    if payload.action == "clear":
        DayOverride.objects.filter(**scope).delete()
        status = None
    else:
        DayOverride.objects.update_or_create(
            **scope, defaults={"status": payload.action}
        )
        status = payload.action

    return {"date": target_date, "status": status}


@router.post(
    "/{employee_id}/{override_date}/",
    auth=HasPerm("schedule.view_shift"),
    response=OverrideResponse,
)
def override(request, employee_id: UUID, override_date: date, payload: OverrideRequest):
    """Create, update, or clear a per-day shift override.

    Authz: HasPerm("schedule.view_shift") gives company admin +
    view_shift up front. The action-specific perm (delete_shift for
    off/reset, add_shift for save) depends on the payload and can't be
    a class — checked below. Matches the HTML set_override view's
    structure (view_shift decorator + is_company_admin + per-action
    perm in body).

    Returns the updated employee row in the same shape as /week/'s
    employees[] so the client replaces its cached copy in one round trip.

    Validation:
    - 422: malformed date in the path, or unknown action / bad payload
      shape. Ninja validates these before the function body runs.
    - 400: no company in context (from HasPerm)
    - 403: not company admin or missing view_shift (from HasPerm), or
      missing the per-action shift perm (from body)
    - 404: employee not in this company, or no longer employed
    - 422: day marked Closed/Holiday, employee not employed on the
      date, or invalid times (bad format, missing one, end<=start)
    """
    if payload.action in ("off", "reset"):
        if not request.user.has_perm("schedule.delete_shift"):
            raise HttpError(403, "Forbidden.")
    else:
        if not request.user.has_perm("schedule.add_shift"):
            raise HttpError(403, "Forbidden.")

    company = request.company

    today = timezone.localdate()
    try:
        employee = (
            Employee.objects.filter(company=company)
            .filter(Q(last_day__isnull=True) | Q(last_day__gte=today))
            .get(pk=employee_id)
        )
    except Employee.DoesNotExist:
        raise HttpError(404, "Employee not found.")

    day_override = DayOverride.objects.filter(
        date=override_date, company=company, team__isnull=True
    ).first()
    if day_override:
        raise HttpError(422, f"This day is marked {day_override.get_status_display()}.")

    if override_date not in _employed_dates(employee, [override_date]):
        raise HttpError(422, "Employee not employed on this date.")

    try:
        result = apply_override(
            employee=employee,
            override_date=override_date,
            action=payload.action,
            start_str=payload.start,
            end_str=payload.end,
            notify=payload.notify,
        )
    except OverrideError as exc:
        raise HttpError(422, str(exc))

    week_start = _week_start(override_date)
    row = week_row_for(company, employee, week_start)

    return {
        "employee": row,
        "notification_sent": result.notification_sent,
        "notification_error": result.notification_error,
    }
