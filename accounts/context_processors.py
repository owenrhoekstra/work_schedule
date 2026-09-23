from django.contrib.auth.models import User


def pending_accounts(request):
    if request.user.is_authenticated and request.user.has_perm("schedule.add_employee"):
        count = User.objects.filter(is_active=False, employee__is_active=True).count()
        return {"pending_accounts_count": count}
    return {}


def user_is_management(request):
    if not request.user.is_authenticated:
        return {"is_management": False}
    is_mgmt = (
        request.user.is_superuser
        or request.user.groups.filter(name="Management").exists()
    )
    return {"is_management": is_mgmt}
