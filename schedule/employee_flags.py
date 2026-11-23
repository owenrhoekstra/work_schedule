from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class FlagDef:
    key: str
    label: str
    get: Callable[[object], bool]
    set: Callable[[object, bool], None]  # must persist
    description: str | None = None
    edit_perm: str | None = None  # None: company admin alone is enough


@dataclass(frozen=True)
class FlagDef:
    key: str
    label: str
    get: Callable[[object], bool]
    set: Callable[[object, bool], None]
    description: str | None = None
    edit_perm: str | None = None
    team_admin_can_edit: bool = False  # opt-in per flag


def model_field_flag(
    key, label, field, *, description=None, edit_perm=None, team_admin_can_edit=False
):
    def _set(employee, value):
        setattr(employee, field, value)
        employee.save(update_fields=[field])

    return FlagDef(
        key,
        label,
        lambda e: bool(getattr(e, field)),
        _set,
        description,
        edit_perm,
        team_admin_can_edit,
    )


def model_field_flag(key, label, field, *, description=None, edit_perm=None):
    """Flag backed by a BooleanField on Employee."""

    def _set(employee, value):
        setattr(employee, field, value)
        employee.save(update_fields=[field])

    return FlagDef(
        key, label, lambda e: bool(getattr(e, field)), _set, description, edit_perm
    )


FLAGS: tuple[FlagDef, ...] = (
    # model_field_flag("can_view_team_schedule", "Can view team schedule", "can_view_team_schedule",
    #                  edit_perm="schedule.change_employee"),
)
FLAGS_BY_KEY = {f.key: f for f in FLAGS}
