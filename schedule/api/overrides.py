"""Override mutation endpoint."""

from datetime import date
from uuid import UUID

from django.db.models import Q
from django.utils import timezone
from ninja import Router
from ninja.errors import HttpError

from schedule.models import DayOverride, Employee
from schedule.scheduling import _employed_dates, _week_start
from schedule.selectors import week_row_for
from schedule.services import OverrideError, apply_override
from work_schedule.api.auth import session_auth

from .schemas import OverrideRequest, OverrideResponse

router = Router(tags=["schedule"], auth=session_auth)


@router.post("/{employee_id}/{date_iso}/", response=OverrideResponse)
def override(
    request,
    employee_id: UUID,
    date_iso: str,
    payload: OverrideRequest,
):
    """Create, update, or clear a per-day shift override.

    Authz mirrors views.set_override: company admin + per-action perm
    (delete_shift for off/reset, add_shift for save). Returns the
    updated employee row in the same shape as /week/'s employees[] so
    the client replaces its cached copy in one round trip.

    Validation:
    - 400: malformed date
    - 403: not company admin, or missing the per-action shift perm
    - 404: employee not in this company, or no longer employed
    - 422: day is marked Closed/Holiday, employee not employed on
      that date, or invalid times (bad format, missing one, end<=start)
    """
    company = request.company
    if company is None:
        raise HttpError(400, "No company in context.")

    today = timezone.localdate()
    try:
        employee = (
            Employee.objects.filter(company=company)
            .filter(Q(last_day__isnull=True) | Q(last_day__gte=today))
            .get(pk=employee_id)
        )
    except Employee.DoesNotExist:
        raise HttpError(404, "Employee not found.")

    try:
        override_date = date.fromisoformat(date_iso)
    except ValueError:
        raise HttpError(400, "Invalid date.")

    # Authz: company admin + per-action perm.
    if not getattr(request, "is_company_admin", False):
        raise HttpError(403, "Company admin required.")
    if payload.action in ("off", "reset"):
        if not request.user.has_perm("schedule.delete_shift"):
            raise HttpError(403, "Missing delete_shift permission.")
    else:
        if not request.user.has_perm("schedule.add_shift"):
            raise HttpError(403, "Missing add_shift permission.")

    # Day-level closed/holiday blocks the mutation. team__isnull=True
    # today — team-scoped DayOverrides are reserved for the teams UI
    # and don't yet affect individual overrides.
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
