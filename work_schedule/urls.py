"""
URL configuration for work_schedule project.
"""

from django.contrib import admin
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordChangeDoneView,
    PasswordChangeView,
)
from django.urls import include, path
from django.views.generic import RedirectView

from accounts.forms import StyledLoginForm, StyledPasswordChangeForm
from accounts.views import OTPGatedPasswordChangeView
from work_schedule import views as project_views

urlpatterns = [
    path("healthz/", project_views.healthz, name="healthz"),
    path("", RedirectView.as_view(url="/schedule/home/")),
    path("back-panel01294/", admin.site.urls),
    # Auth
    path(
        "accounts/login/",
        LoginView.as_view(
            authentication_form=StyledLoginForm,
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path(
        "accounts/logout/",
        LogoutView.as_view(),
        name="logout",
    ),
    path(
        "accounts/password_change/",
        OTPGatedPasswordChangeView.as_view(),
        name="password_change",
    ),
    path(
        "accounts/password_change/done/",
        PasswordChangeDoneView.as_view(),
        name="password_change_done",
    ),
    # App URLs
    path("accounts/", include("accounts.urls")),
    path("schedule/", include("schedule.urls")),
]
