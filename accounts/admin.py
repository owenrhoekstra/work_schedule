from axes.models import AccessAttempt, AccessLog
from django.contrib import admin
from django.contrib.admin.exceptions import NotRegistered

# Axes registers these itself in axes/admin.py. Unregister them first so we
# can re-register with superuser-only permissions.
try:
    admin.site.unregister(AccessAttempt)
except NotRegistered:
    pass

try:
    admin.site.unregister(AccessLog)
except NotRegistered:
    pass


@admin.register(AccessAttempt)
class AccessAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "username",
        "ip_address",
        "failures_since_start",
        "attempt_time",
    )
    list_filter = ("username", "ip_address")
    search_fields = ("username", "ip_address")
    ordering = ("-attempt_time",)

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(AccessLog)
class AccessLogAdmin(admin.ModelAdmin):
    list_display = ("username", "ip_address", "attempt_time", "logout_time")
    list_filter = ("username", "ip_address")
    search_fields = ("username", "ip_address")
    ordering = ("-attempt_time",)

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
