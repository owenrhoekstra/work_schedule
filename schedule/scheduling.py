"""Pure scheduling helpers.

No request objects, no HTTP concerns. Importable by views, services,
and selectors without creating a cycle.

The underscore prefix on most functions is historical — they were
private helpers inside views.py before this extraction. Treat them as
module-level utilities here; dropping the prefix is a follow-up
commit that avoids touching ~50 call sites right now.
"""

from datetime import datetime, timedelta

from django.conf import settings
from django.db.models import Min, Q
from django.utils import timezone

from .models import Employee, EmploymentPeriod

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DAYS = [0, 1, 2, 3, 4, 5]
DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
DAY_LABELS_FULL = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
]
WEEK_LABELS = ["A", "B", "C", "D"]
MAX_CYCLE_WEEKS = 4
MAX_PRINT_WEEKS = 4

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


# ---------------------------------------------------------------------------
# Parsing and formatting
# ---------------------------------------------------------------------------


def _parse_time(value):
    """Parse a user-entered time string. Returns None if empty.

    Raises ValueError if the string can't be parsed.
    """
    value = (value or "").strip()
    if not value:
        return None
    normalized = value.replace(".", ":").upper()
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(normalized, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Could not understand the time {value!r}.")


def _format_duration(td):
    """Format a timedelta as 'Hh MMm'."""
    total_minutes = int(td.total_seconds() // 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}h {minutes:02d}m"


def _format_time_12(t):
    """Format a time as '9:00 AM' (no leading zero on the hour)."""
    s = t.strftime("%I:%M %p")
    return s.removeprefix("0")


def _ordinal(n):
    """1 -> '1st', 2 -> '2nd', 3 -> '3rd', 4 -> '4th', 11 -> '11th', ..."""
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


# ---------------------------------------------------------------------------
# Week helpers
# ---------------------------------------------------------------------------


def _week_start(d):
    """Return the Monday of the week containing d."""
    return d - timedelta(days=d.weekday())


def _week_title_for(week_start):
    """Human title for a week, with ordinal day and year when it differs."""
    current_week = _week_start(timezone.localdate())
    day_with_ordinal = _ordinal(week_start.day)
    if week_start.year == current_week.year:
        return f"Week of {week_start.strftime('%B')} {day_with_ordinal}"
    return f"Week of {week_start.strftime('%B')} {day_with_ordinal}, {week_start.year}"


def _earliest_week(company):
    """Monday of the week containing the oldest employment period start."""
    earliest = EmploymentPeriod.objects.filter(company=company).aggregate(
        d=Min("start_date")
    )["d"]
    if earliest is None:
        return None
    return _week_start(earliest)


# ---------------------------------------------------------------------------
# Pattern and cycle
# ---------------------------------------------------------------------------


def _pattern_for_week(employee, week_start):
    """The ShiftPattern active for the week starting week_start.

    effective_to is exclusive; None is open-ended. If multiple patterns
    match (transition-era overlap), the one with the greatest
    effective_from wins.
    """
    candidates = [
        p
        for p in employee.patterns.all()
        if p.effective_from <= week_start
        and (p.effective_to is None or week_start < p.effective_to)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.effective_from)


def _cycle_offset(week_start, cycle_weeks):
    """Which week of a cycle_weeks-long cycle the given week falls on."""
    if cycle_weeks <= 1:
        return 0
    weeks_since_epoch = (week_start - settings.CYCLE_EPOCH).days // 7
    return weeks_since_epoch % cycle_weeks


def _week_offset_for(week_start, pattern):
    """Which week of this pattern's cycle the given week falls on."""
    return _cycle_offset(week_start, pattern.cycle_weeks)


# ---------------------------------------------------------------------------
# Employment
# ---------------------------------------------------------------------------


def _employees_for_week(week_start, company):
    """Employees with any employment period overlapping this week.

    Ordering: start_date ascending. The old role-based ordering is gone
    (roles now live per-team); Branch B replaces this with team grouping.
    Between Branch A and Branch B, the roster is start-date-sorted.

    Prefetches team_links + team + role so _employee_week_row can
    derive the default team's name and role without N+1 queries.
    """
    week_end = week_start + timedelta(days=5)
    return (
        Employee.objects.filter(company=company)
        .filter(
            Q(periods__start_date__lte=week_end)
            & (Q(periods__end_date__isnull=True) | Q(periods__end_date__gt=week_start))
        )
        .distinct()
        .select_related("title", "role")
        .prefetch_related(
            "periods",
            "patterns__shifts",
            "team_links__team",
            "team_links__role",
        )
        .order_by("start_date")
    )


def _employed_dates(employee, week_dates):
    """Set of dates in week_dates covered by any employment period."""
    covered = set()
    for period in employee.periods.all():
        for d in week_dates:
            if period.start_date <= d and (
                period.end_date is None or period.end_date > d
            ):
                covered.add(d)
    return covered


# ---------------------------------------------------------------------------
# Shift display
# ---------------------------------------------------------------------------


def _shift_display(shift):
    """Human-readable shift display, or None."""
    if shift is None:
        return None
    return f"{_format_time_12(shift.start_time)} – {_format_time_12(shift.end_time)}"


def _cell_display(employee, d):
    """What the schedule cell shows for this employee on this date.

    Overrides take precedence; otherwise the default from the pattern
    active that week.
    """
    override = employee.overrides.filter(date=d).first()
    if override:
        if override.is_off:
            return "OFF"
        return (
            f"{_format_time_12(override.start_time)} – "
            f"{_format_time_12(override.end_time)}"
        )

    week_start = _week_start(d)
    pattern = _pattern_for_week(employee, week_start)
    if pattern is None:
        return "OFF"

    offset = _week_offset_for(week_start, pattern)
    day = d.weekday()
    default = pattern.shifts.filter(week_offset=offset, day=day).first()
    if default:
        return (
            f"{_format_time_12(default.start_time)} – "
            f"{_format_time_12(default.end_time)}"
        )
    return "OFF"


def _last_week_of(pattern):
    """The Monday of the last week this pattern covers, or None if open-ended.

    effective_to is exclusive — the first week *not* covered — so the
    last covered week starts seven days earlier. Used for display copy
    only; resolution logic uses effective_to directly.
    """
    if pattern is None or pattern.effective_to is None:
        return None
    return pattern.effective_to - timedelta(days=7)


def _pattern_summary(pattern):
    """Render-ready rows for a pattern, grouped by cycle week.

    Returns a list of dicts, one per week in the cycle:
        {"label": "A", "rows": [{"label": "Monday", "shift": <Shift or None>}, ...]}

    Used by the Saved Patterns list to show the hours inside each
    saved pattern without firing a query per pattern.
    """
    shifts_by_key = {(s.week_offset, s.day): s for s in pattern.shifts.all()}
    weeks = []
    for offset in range(pattern.cycle_weeks):
        rows = [
            {
                "label": DAY_LABELS_FULL[day],
                "shift": shifts_by_key.get((offset, day)),
            }
            for day in DAYS
        ]
        weeks.append({"label": WEEK_LABELS[offset], "rows": rows})
    return weeks
