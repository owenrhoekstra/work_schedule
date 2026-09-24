from django.contrib.auth.models import User


def pending_accounts(request):
    if not request.user.is_authenticated or not request.user.has_perm(
        "schedule.add_employee"
    ):
        return {}
    try:
        count = User.objects.filter(is_active=False, employee__is_active=True).count()
    except Exception:
        return {}
    return {"pending_accounts_count": count}


def user_is_management(request):
    if not request.user.is_authenticated:
        return {"is_management": False}
    try:
        is_mgmt = (
            request.user.is_superuser
            or request.user.groups.filter(name="Management").exists()
        )
    except Exception:
        return {"is_management": False}
    return {"is_management": is_mgmt}
