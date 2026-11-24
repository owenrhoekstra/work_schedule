"""Response schemas for /api/v1/schedule/ endpoints."""

import datetime
from typing import Literal
from uuid import UUID

from ninja import Schema

CellKind = Literal[
    "default",
    "override",
    "off_override",
    "day_override",
    "not_employed",
    "none",
]


class CycleRef(Schema):
    label: str
    offset: int
    total: int


class Cell(Schema):
    date: str
    weekday: int
    kind: CellKind
    start: str | None
    end: str | None
    has_override: bool
    is_employed: bool
    # The pattern's default for this day, regardless of override state.
    # Enables optimistic reset on the client: the popover can compute
    # what the cell will look like when "Reset to default" is clicked
    # without a round trip. Null when the pattern has no default shift
    # for this day, or when no pattern covers the week.
    default_start: str | None
    default_end: str | None


class ViewerCan(Schema):
    # Split from a combined `set_override` per Session 10's "button's
    # gate equals endpoint's perm" rule: Save gates on add_shift,
    # Mark off / Reset gate on delete_shift. Cell is clickable when
    # either is true.
    can_add_shift: bool
    can_delete_shift: bool
    change_employee_day_override: bool
    change_day_override: bool
    add_employee: bool
    print: bool


class OverrideRequest(Schema):
    action: Literal["save", "off", "reset"]
    start: str | None = None
    end: str | None = None
    notify: bool = False


class OverrideResponse(Schema):
    # Full updated employee row so the client can replace its cached
    # copy in one round trip. Same WeekEmployee shape as /week/'s
    # employees[] — no separate schema for "the same employee after a
    # mutation."
    employee: WeekEmployee
    notification_sent: bool
    notification_error: str | None


class DayHeader(Schema):
    date: str
    weekday: int
    short_label: str
    long_label: str
    date_label: str
    override_status: str | None


class WeekEmployee(Schema):
    id: str
    first_name: str
    last_name: str
    display_name: str
    role_id: str | None
    role_name: str | None
    last_day: str | None
    cycle: CycleRef | None
    cells: list[Cell]
    total_minutes: int


class WeekRef(Schema):
    start: str
    title: str
    prev: str
    next: str
    is_current: bool
    can_go_back: bool


class WeekResponse(Schema):
    week: WeekRef
    days: list[DayHeader]
    scope: str
    available_scopes: list[str]
    employees: list[WeekEmployee]
    viewer_can: ViewerCan


class DayOverrideIn(Schema):
    action: Literal["closed", "holiday", "clear"]


class DayOverrideOut(Schema):
    date: datetime.date
    status: Literal["closed", "holiday"] | None


class EmployeeFlagOut(Schema):
    key: str
    label: str
    description: str | None
    value: bool
    can_edit: bool


class PatternDayOut(Schema):
    label: str
    start: str | None  # "HH:MM"
    end: str | None


class PatternWeekOut(Schema):
    label: str
    days: list[PatternDayOut]


class PatternSummaryOut(Schema):
    effective_from: datetime.date
    through: datetime.date | None
    cycle_weeks: int
    current_cycle_label: str | None
    weeks: list[PatternWeekOut]


class EmployeeCan(Schema):
    send_welcome: bool


class EmployeeDetailOut(Schema):
    id: UUID
    email: str | None  # admins only
    start_date: datetime.date
    last_day: datetime.date | None
    flags: list[EmployeeFlagOut]
    pattern: PatternSummaryOut | None
    can: EmployeeCan


class FlagIn(Schema):
    key: str
    value: bool


class WelcomeOut(Schema):
    sent: bool
