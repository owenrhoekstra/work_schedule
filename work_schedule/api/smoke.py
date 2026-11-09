"""Smoke endpoint for /api/v1/.

Not a product API surface — exists to verify session auth, the
public schema shape, and 401 handling end-to-end in Branch 0, and
to give the Vue SPA a trivial endpoint to hit while it's being
wired. Keep it as long as it's useful; delete when the first real
endpoint covers the same ground.
"""

from ninja import Router, Schema

from work_schedule.api.auth import session_auth


router = Router(tags=["smoke"])


class MeSchema(Schema):
    id: int
    email: str
    is_staff: bool


@router.get("/me/", auth=session_auth, response=MeSchema)
def me(request):
    user = request.user
    return {"id": user.id, "email": user.email, "is_staff": user.is_staff}