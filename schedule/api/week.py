"""Weekly schedule endpoint."""

from datetime import date, timedelta

from django.utils import timezone
from ninja import Router
from ninja.errors import HttpError

from schedule.selectors import available_scopes_for, week_schedule_for_scope
from work_schedule.api.auth import session_auth

from .schemas import WeekResponse

router = Router(tags=["schedule"], auth=session_auth)


@router.get("/week/", response=WeekResponse)
def week(request, week: str | None = None, scope: str = "me"):
    """Return one week's schedule for the requested scope.

    `scope ∈ {"me", "team", "company"}`. The scope must be present in
    available_scopes_for(company, user); otherwise 403. The SPA reads
    available_scopes from /me/ to pick a safe default and to render
    the scope selector.

    `week` is an ISO date; any date within the target week is accepted
    and resolved to that week's Monday. Omitted → current week.
    """
    company = request.company
    if company is None:
        raise HttpError(400, "No company in context.")

    if scope not in ("me", "team", "company"):
        raise HttpError(400, f"Unknown scope: {scope!r}")

    allowed = available_scopes_for(company, request.user)
    if scope not in allowed:
        raise HttpError(403, f"Scope {scope!r} not available.")

    if week is None:
        week_start = timezone.localdate() - timedelta(
            days=timezone.localdate().weekday()
        )
    else:
        try:
            d = date.fromisoformat(week)
        except ValueError:
            raise HttpError(400, "Invalid week format.")
        week_start = d - timedelta(days=d.weekday())

    return week_schedule_for_scope(
        company, week_start, scope, request.user, request.team
    )
