from django.urls import path

from . import views

urlpatterns = [
    path("home/", views.home, name="home"),
    path("employees/add/", views.add_employee, name="add_employee"),
    path(
        "employees/<int:pk>/defaults/",
        views.employee_defaults,
        name="employee_defaults",
    ),
    path(
        "overrides/<int:employee_pk>/<str:date_iso>/",
        views.set_override,
        name="set_override",
    ),
    path("settings/", views.settings_home, name="settings_home"),
    path(
        "settings/employees/<int:pk>/edit/",
        views.settings_edit_employee,
        name="settings_edit_employee",
    ),
    path(
        "settings/employees/<int:pk>/deactivate/",
        views.settings_deactivate_employee,
        name="settings_deactivate_employee",
    ),
    path(
        "settings/titles/add/",
        views.settings_add_title,
        name="settings_add_title",
    ),
    path(
        "settings/titles/<int:pk>/delete/",
        views.settings_delete_title,
        name="settings_delete_title",
    ),
    path(
        "settings/roles/add/",
        views.settings_add_role,
        name="settings_add_role",
    ),
    path(
        "settings/roles/<int:pk>/delete/",
        views.settings_delete_role,
        name="settings_delete_role",
    ),
    path(
        "settings/roles/<int:pk>/move/<str:direction>/",
        views.settings_move_role,
        name="settings_move_role",
    ),
    path(
        "settings/employees/<int:pk>/cancel-deactivation/",
        views.settings_cancel_deactivation,
        name="settings_cancel_deactivation",
    ),
]
