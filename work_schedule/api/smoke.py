"""Smoke endpoint for /api/v1/.

Not a product API surface — exists to verify session auth, the public
schema shape, and 401 handling end-to-end, and to give the Vue SPA a
trivial endpoint to hit while it's being wired.
"""

from ninja import Router

from work_schedule.api.auth import session_auth
from work_schedule.api.schemas import MeSchema

router = Router(tags=["smoke"])


@router.get("/me/", auth=session_auth, response=MeSchema)
def me(request):
    user = request.user
    return {"id": user.id, "email": user.email, "is_staff": user.is_staff}
