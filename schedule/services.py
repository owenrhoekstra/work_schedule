"""Write-side services for the schedule app.

Pure mutations that both the Django HTML views and the Ninja API
endpoints call. No HTTP concerns, no authz — callers validate
permissions and day-override state before invoking.

Companion to selectors.py (reads). Together they're the seam that lets
HTML and API stay consistent as the SPA replaces Django templates.
"""

from dataclasses import dataclass
from datetime import date

from django.db import transaction

from . import notifications
from .models import Employee, ShiftOverride
from .scheduling import _cell_display, _ordinal, _parse_time


class OverrideError(Exception):
    """Raised when an override mutation is rejected."""


@dataclass
class OverrideResult:
    previous_display: str
    new_display: str
    notification_sent: bool
    notification_error: str | None


@transaction.atomic
def apply_override(
    employee: Employee,
    override_date: date,
    action: str,
    start_str: str | None,
    end_str: str | None,
    notify: bool,
) -> OverrideResult:
    """Create, update, or clear a per-day shift override.

    Mirrors the mutation half of views.set_override. Returns
    OverrideResult with the display before and after plus notification
    outcome. Raises OverrideError for invalid input.

    `action`:
        "save"  — set start_time/end_time from start_str/end_str
        "off"   — mark the day off entirely
        "reset" — delete the override, falling back to the default pattern

    Notifications are sent only when `notify` is set AND the display
    actually changed. A no-op save with notify=True returns
    notification_sent=False, notification_error=None — no message, no
    email, matching the Django view's pre-refactor behavior.
    """
    if action not in ("save", "off", "reset"):
        raise OverrideError(f"Unknown action: {action!r}")

    previous_display = _cell_display(employee, override_date)

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
            start = _parse_time(start_str)
            end = _parse_time(end_str)
        except ValueError as exc:
            raise OverrideError(str(exc)) from exc
        if start is None or end is None:
            raise OverrideError("Set both start and end time.")
        if end <= start:
            raise OverrideError("End time must be after start time.")
        ShiftOverride.objects.update_or_create(
            employee=employee,
            date=override_date,
            defaults={"is_off": False, "start_time": start, "end_time": end},
        )

    new_display = _cell_display(employee, override_date)

    notification_sent = False
    notification_error: str | None = None
    if notify and previous_display != new_display:
        ok, error = notifications.send_shift_changes_email(
            employee,
            [
                {
                    "label": override_date.strftime("%A, %B ")
                    + _ordinal(override_date.day),
                    "old": previous_display,
                    "new": new_display,
                }
            ],
            kind="override",
        )
        notification_sent = ok
        notification_error = None if ok else error

    return OverrideResult(
        previous_display=previous_display,
        new_display=new_display,
        notification_sent=notification_sent,
        notification_error=notification_error,
    )
