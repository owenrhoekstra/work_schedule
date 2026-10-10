from django.urls import path

from . import views

urlpatterns = [
    path("home/", views.home, name="home"),
    path("employees/add/", views.add_employee, name="add_employee"),
    path(
        "employees/<uuid:pk>/defaults/",
        views.employee_defaults,
        name="employee_defaults",
    ),
    path(
        "patterns/<uuid:pk>/delete/",
        views.delete_pattern,
        name="delete_pattern",
    ),
    path(
        "overrides/<uuid:employee_pk>/<str:date_iso>/",
        views.set_override,
        name="set_override",
    ),
    path(
        "days/<str:date_iso>/",
        views.set_day_override,
        name="set_day_override",
    ),
    path("settings/", views.settings_home, name="settings_home"),
    path(
        "settings/employees/<uuid:pk>/deactivate/",
        views.settings_deactivate_employee,
        name="settings_deactivate_employee",
    ),
    path(
        "settings/employees/<uuid:pk>/cancel-deactivation/",
        views.settings_cancel_deactivation,
        name="settings_cancel_deactivation",
    ),
    path(
        "settings/employees/<uuid:pk>/reactivate/",
        views.settings_reactivate_employee,
        name="settings_reactivate_employee",
    ),
    path(
        "settings/employees/<uuid:pk>/send-welcome/",
        views.send_welcome,
        name="send_welcome",
    ),
    path(
        "settings/titles/add/",
        views.settings_add_title,
        name="settings_add_title",
    ),
    path(
        "settings/titles/<uuid:pk>/delete/",
        views.settings_delete_title,
        name="settings_delete_title",
    ),
    path(
        "settings/roles/add/",
        views.settings_add_role,
        name="settings_add_role",
    ),
    path(
        "settings/roles/<uuid:pk>/delete/",
        views.settings_delete_role,
        name="settings_delete_role",
    ),
    path(
        "settings/roles/<uuid:pk>/move/<str:direction>/",
        views.settings_move_role,
        name="settings_move_role",
    ),
    path("print/", views.print_schedule, name="print_schedule"),
    path("qr/", views.qr_code, name="qr_code"),
]
