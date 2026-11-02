"""
URL configuration for work_schedule project.
"""

from datetime import datetime, timedelta

from django.contrib import admin
from django.contrib.admin.exceptions import NotRegistered
from django.contrib.auth.admin import UserAdmin as _BaseUserAdmin
from django.contrib.auth.models import User as _AuthUser
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordChangeDoneView,
)
from django.shortcuts import redirect
from django.urls import include, path, reverse
from django.utils import timezone
from django.views.generic import RedirectView

from accounts.forms import StyledLoginForm
from accounts.views import OTPGatedPasswordChangeView
from work_schedule import views as project_views


# ---------------------------------------------------------------------------
# Admin password-change gating
#
# Django exposes two self-service password-change entry points under
# /admin/, and only the first was covered by the original override:
#
#   /admin/password_change/          AdminSite.password_change
#                                     self only; internally redirects to
#                                     the per-user route below
#   /admin/auth/user/<id>/password/  UserAdmin.password_change_view
#                                     self AND other-user reset
#
# The first is a pure redirect handler — no form. The second is where
# the form actually renders, and where anyone can reach the flow
# directly. Without intercepting BOTH, the OTP gate is bypassable.
#
# Two overrides below:
#   1. admin.site.password_change -> redirect to the accounts flow,
#      matching the canonical self-service surface.
#   2. UserAdmin.get_urls() -> swap the per-user route for a wrapper
#      that requires a fresh OTP, then delegates to user_change_password.
# ---------------------------------------------------------------------------


def _recently_verified(request, ttl=timedelta(minutes=5)):
    """Mirror of OTPGatedPasswordChangeView._recently_verified.

    Duplicated rather than imported to keep urls.py independent of
    accounts.views internals. The session key (`otp_verified_at`) and
    its ISO timestamp format are the stable contract; the helper
    method is an implementation detail.

    Returns True if the session carries a fresh OTP verification stamp.
    Clears the stale stamp if it's beyond `ttl`.
    """
    raw = request.session.get("otp_verified_at")
    if not raw:
        return False
    try:
        ts = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return False
    if timezone.is_naive(ts):
        ts = timezone.make_aware(ts)
    if timezone.now() - ts > ttl:
        request.session.pop("otp_verified_at", None)
        return False
    return True


def _admin_password_change_redirect(request, extra_context=None):
    """Force /admin/password_change/ through the OTP-gated accounts flow.

    The default AdminSite.password_change redirects to the per-user
    route (admin:auth_user_password_change) with the current user's id.
    Our override sends the user to /accounts/password_change/ instead
    so the canonical self-service surface is one place, and the
    OTP-gated view is the first thing they hit.
    """
    return redirect("password_change")


admin.site.password_change = _admin_password_change_redirect


class _OTPGatedUserAdmin(_BaseUserAdmin):
    """UserAdmin whose per-user password-change route requires OTP.

    Covers both:
      - self-change (id == request.user.pk) — a legitimate self-service
        path that bypasses admin.site.password_change by being typed
        or bookmarked directly
      - other-user reset (id != request.user.pk) — governed by
        has_change_permission (auth.change_user)

    Existing authorization stays in place: admin_view (is_active +
    is_staff + has_permission) still runs first, and user_change_password
    still checks has_change_permission before rendering or saving.

    Two additions on top of stock UserAdmin:
      1. Require a fresh `otp_verified_at` stamp before delegating.
      2. Clear the stamp on a successful POST so one OTP unlocks one
         change — matches OTPGatedPasswordChangeView.form_valid.
    """

    def get_urls(self):
        # Replace the default auth_user_password_change route with a
        # wrapper. Everything else stays untouched.
        urls = super().get_urls()
        result = []
        for url in urls:
            if url.name == "auth_user_password_change":
                result.append(
                    path(
                        "<path:object_id>/password/",
                        self.admin_site.admin_view(self._otp_gated_password_change),
                        name="auth_user_password_change",
                    )
                )
            else:
                result.append(url)
        return result

    def _otp_gated_password_change(self, request, object_id):
        # No fresh OTP -> send through verify_otp with the current URL
        # as `next`, so the user lands back here after passing the gate.
        if not _recently_verified(request):
            verify_url = reverse("verify_otp")
            return redirect(f"{verify_url}?next={request.path}")
        # OTP is fresh — delegate to the parent method. It handles:
        #   - has_change_permission (auth.change_user) check
        #   - AdminPasswordChangeForm vs PasswordChangeForm (self vs other)
        #   - all form rendering and POST handling
        response = self.user_change_password(request, object_id)

        # Clear the OTP stamp only on successful save, matching
        # OTPGatedPasswordChangeView.form_valid's behavior. One OTP
        # unlocks one password change; GETs and validation-error POSTs
        # preserve the stamp so the user can retry without re-verifying.
        #
        # user_change_password returns a redirect on success and a
        # TemplateResponse otherwise — the status check distinguishes
        # the two without re-inspecting the form.
        if request.method == "POST" and response.status_code in (
            301, 302, 303, 307, 308
        ):
            request.session.pop("otp_verified_at", None)

        return response


try:
    admin.site.unregister(_AuthUser)
except NotRegistered:
    pass
admin.site.register(_AuthUser, _OTPGatedUserAdmin)


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