"""Router aggregation for the schedule app's /api/v1/ endpoints."""

from ninja import Router

from .employees import router as employees_router
from .overrides import router as overrides_router
from .week import router as week_router

router = Router(tags=["schedule"])
router.add_router("/", week_router)
router.add_router("/overrides/", overrides_router)
router.add_router("/employees/", employees_router)
