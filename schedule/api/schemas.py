"""Response schemas for /api/v1/schedule/ endpoints."""

from typing import Literal

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


class ViewerCan(Schema):
    set_override: bool
    set_day_override: bool
    add_employee: bool
    print: bool


class WeekResponse(Schema):
    week: WeekRef
    days: list[DayHeader]
    scope: str
    available_scopes: list[str]
    employees: list[WeekEmployee]
    viewer_can: ViewerCan