# schedule/api/__init__.py
"""Router aggregation for the schedule app's /api/v1/ endpoints."""

from ninja import Router

from .week import router as week_router

router = Router(tags=["schedule"])
router.add_router("/", week_router)