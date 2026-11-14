from django.contrib import admin

from .models import (
    Company,
    CompanyMembership,
    DayOverride,
    Employee,
    EmployeeTeam,
    EmploymentPeriod,
    Role,
    Shift,
    ShiftOverride,
    ShiftPattern,
    Team,
    TeamMembership,
    Title,
)


@admin.register(Title)
class TitleAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "team", "display_order", "show_in_name")
    list_editable = ("display_order", "show_in_name")
    list_filter = ("company", "team")
    search_fields = ("name",)
    ordering = ("display_order", "name")


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "team", "display_order")
    list_editable = ("display_order",)
    list_filter = ("company", "team")
    ordering = ("display_order", "name")
    search_fields = ("name",)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("__str__", "company", "role", "email", "is_active")
    list_filter = ("is_active", "company", "role")
    search_fields = ("first_name", "last_name", "email")


@admin.register(ShiftPattern)
class ShiftPatternAdmin(admin.ModelAdmin):
    list_display = ("employee", "effective_from", "cycle_weeks")
    list_filter = ("cycle_weeks",)
    search_fields = ("employee__first_name", "employee__last_name")
    autocomplete_fields = ("employee",)


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ("pattern", "day", "start_time", "end_time")
    list_filter = ("day",)
    search_fields = ("pattern__employee__first_name", "pattern__employee__last_name")
    autocomplete_fields = ("pattern",)


@admin.register(ShiftOverride)
class ShiftOverrideAdmin(admin.ModelAdmin):
    list_display = ("employee", "date", "is_off", "start_time", "end_time")
    list_filter = ("is_off", "date")
    autocomplete_fields = ("employee",)


@admin.register(EmploymentPeriod)
class EmploymentPeriodAdmin(admin.ModelAdmin):
    list_display = ("employee", "start_date", "end_date")
    list_filter = ("end_date",)
    search_fields = (
        "employee__first_name",
        "employee__last_name",
        "employee__email",
    )
    raw_id_fields = ("employee",)
    list_select_related = ("employee",)
    date_hierarchy = "start_date"
    ordering = ("-start_date",)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "allow_member_view_all")
    list_filter = ("company", "allow_member_view_all")
    search_fields = ("name",)
    raw_id_fields = ("company",)


@admin.register(CompanyMembership)
class CompanyMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "company", "role", "status", "created_at")
    list_filter = ("role", "status", "company")
    search_fields = ("user__username", "user__email", "company__name")
    raw_id_fields = ("user", "company")


@admin.register(TeamMembership)
class TeamMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "team", "role", "valid_from", "valid_to")
    list_filter = ("role", "team__company")
    search_fields = ("user__username", "user__email", "team__name")
    raw_id_fields = ("user", "team")


@admin.register(EmployeeTeam)
class EmployeeTeamAdmin(admin.ModelAdmin):
    list_display = ("employee", "team", "is_default", "valid_from", "valid_to")
    list_filter = ("is_default", "team__company")
    search_fields = (
        "employee__first_name",
        "employee__last_name",
        "employee__email",
        "team__name",
    )
    raw_id_fields = ("employee", "team")


@admin.register(DayOverride)
class DayOverrideAdmin(admin.ModelAdmin):
    list_display = ("date", "company", "team", "status")
    list_filter = ("status", "company", "date")
    search_fields = ("company__name",)
    date_hierarchy = "date"
    raw_id_fields = ("company", "team")
    ordering = ("-date",)