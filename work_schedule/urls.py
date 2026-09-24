from django.contrib import admin
from django.contrib.auth.views import LoginView
from django.urls import include, path
from django.views.generic import RedirectView

from accounts.forms import StyledLoginForm
from work_schedule import views as project_views

urlpatterns = [
    path("healthz/", project_views.healthz, name="healthz"),
    path("", RedirectView.as_view(url="/schedule/home/")),
    path("back-panel01294/", admin.site.urls),
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
