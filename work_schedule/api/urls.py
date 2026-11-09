"""Router registration for /api/v1/.

Called explicitly from `work_schedule/urls.py` before the
`urlpatterns` list is evaluated — `api.urls` snapshots the
registered routers at access time, so registration must precede
the mount.
"""

from accounts.api import router as accounts_router
from schedule.api import router as schedule_router
from work_schedule.api.api import api
from work_schedule.api.smoke import router as smoke_router


def register_routers() -> None:
    api.add_router("/smoke/", smoke_router)
    api.add_router("/schedule/", schedule_router)
    api.add_router("/accounts/", accounts_router)