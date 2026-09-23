from django.urls import path

from . import views

urlpatterns = [
    # path('profile/', views.profile, name='profile'),
    path("signup/", views.signup, name="signup"),
    path("pending/", views.pending_accounts, name="pending_accounts"),
    path(
        "pending/<int:user_id>/approve/", views.approve_account, name="approve_account"
    ),
]
