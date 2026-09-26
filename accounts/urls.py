from django.urls import path

from . import views

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("profile/", views.profile, name="profile"),
    path("verify-otp/", views.verify_otp, name="verify_otp"),
    path("pending/", views.pending_accounts, name="pending_accounts"),
    path(
        "pending/<int:user_id>/approve/",
        views.approve_account,
        name="approve_account",
    ),
]
