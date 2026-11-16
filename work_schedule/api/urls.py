"""Router registration for /api/v1/."""

from accounts.api import me_router
from accounts.api import router as accounts_router
from schedule.api import router as schedule_router
from work_schedule.api.api import api
from work_schedule.api.smoke import router as smoke_router


def register_routers() -> None:
    api.add_router("/smoke/", smoke_router)
    api.add_router("/me/", me_router)
    api.add_router("/schedule/", schedule_router)
    api.add_router("/companies/", accounts_router)
