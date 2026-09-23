"""
URL configuration for work_schedule project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
"""

from django.contrib import admin
from django.contrib.auth.views import LoginView
from django.urls import include, path
from django.views.generic import RedirectView

from accounts.forms import StyledLoginForm

urlpatterns = [
    path("", RedirectView.as_view(url="/schedule/home/")),
    path("admin/", admin.site.urls),
    path(
        "accounts/login/",
        LoginView.as_view(
            authentication_form=StyledLoginForm,
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path("accounts/", include("django.contrib.auth.urls")),
    path("accounts/", include("accounts.urls")),
    path("schedule/", include("schedule.urls")),
]
