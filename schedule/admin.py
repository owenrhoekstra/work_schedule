from django.contrib import admin

from .models import Employee, Role, Shift, ShiftOverride, Title


@admin.register(Title)
class TitleAdmin(admin.ModelAdmin):
    list_display = ("name", "display_order", "show_in_name")
    list_editable = ("display_order", "show_in_name")
    ordering = ("display_order", "name")


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "display_order")
    list_editable = ("display_order",)
    ordering = ("display_order", "name")
    search_fields = ("name",)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("__str__", "role", "email", "is_active")
    list_filter = ("is_active", "role")
    search_fields = ("first_name", "last_name", "email")


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ("employee", "day", "start_time", "end_time")
    list_filter = ("day",)
    autocomplete_fields = ("employee",)


@admin.register(ShiftOverride)
class ShiftOverrideAdmin(admin.ModelAdmin):
    list_display = ("employee", "date", "is_off", "start_time", "end_time")
    list_filter = ("is_off", "date")
    autocomplete_fields = ("employee",)
