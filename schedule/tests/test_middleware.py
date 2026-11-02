from datetime import date, timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .factories import (
    make_employee,
    make_management_user,
    make_role,
    make_staff_user,
)

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


@override_settings(CACHES=_LOCMEM_CACHES)
class EmployeeDeactivationMiddlewareTests(TestCase):
    def _make_emp_with_user(self, last_day):
        user = make_staff_user(f"u{timezone.now().timestamp()}")
        emp = make_employee(email=user.email)
        emp.user = user
        emp.last_day = last_day
        emp.save()
        user.is_active = True
        user.save(update_fields=["is_active"])
        return user, emp

    def test_past_last_day_kicks_user_out(self):
        user, _ = self._make_emp_with_user(timezone.localdate() - timedelta(days=1))
        self.client.force_login(user)
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_today_is_still_allowed(self):
        user, _ = self._make_emp_with_user(timezone.localdate())
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)

    def test_future_last_day_allowed(self):
        user, _ = self._make_emp_with_user(timezone.localdate() + timedelta(days=30))
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)

    def test_user_without_employee_passes_through(self):
        user = make_staff_user("noemployee")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)

    def test_anonymous_untouched(self):
        # Anonymous should redirect to login via @login_required, not the middleware
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.status_code, 302)


@override_settings(CACHES=_LOCMEM_CACHES)
class HTMXLoginRedirectMiddlewareTests(TestCase):
    """HTMX requests with expired auth should return HX-Redirect, not
    swap the login page into a fragment slot.

    Session expiry shows up as an anonymous POST/GET that hits an
    @login_required view, which Django answers with 302 → login. HTMX
    would follow that redirect and swap the login page into hx-target.
    The middleware rewrites to 204 + HX-Redirect so HTMX does a full-
    page navigation to the login flow.
    """

    def setUp(self):
        self.role = make_role()
        self.emp = make_employee(role=self.role, with_pattern=True)

    # ----- expired session (anonymous) -----

    def test_htmx_post_without_session_returns_hx_redirect(self):
        resp = self.client.post(
            reverse("schedule_change", args=[self.emp.pk]),
            {"effective_from": "2026-01-05", "cycle_weeks": "1"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 204)
        self.assertIn("/accounts/login/", resp["HX-Redirect"])

    def test_htmx_get_without_session_returns_hx_redirect(self):
        resp = self.client.get(
            reverse("schedule_change", args=[self.emp.pk]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 204)
        self.assertIn("/accounts/login/", resp["HX-Redirect"])

    def test_hx_redirect_preserves_next_param(self):
        resp = self.client.post(
            reverse("schedule_change", args=[self.emp.pk]),
            {"effective_from": "2026-01-05", "cycle_weeks": "1"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 204)
        # Django's @login_required appends ?next=<path>. Preserved so
        # the login view can bounce back after re-auth.
        self.assertIn("next=", resp["HX-Redirect"])
        self.assertIn(
            reverse("schedule_change", args=[self.emp.pk]), resp["HX-Redirect"]
        )

    # ----- non-HTMX path untouched -----

    def test_plain_post_without_session_still_gets_302(self):
        resp = self.client.post(
            reverse("schedule_change", args=[self.emp.pk]),
            {"effective_from": "2026-01-05", "cycle_weeks": "1"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp["Location"])
        self.assertNotIn("HX-Redirect", resp)

    def test_plain_get_without_session_still_gets_302(self):
        resp = self.client.get(reverse("schedule_change", args=[self.emp.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn("HX-Redirect", resp)

    # ----- authenticated HTMX path untouched -----

    def test_htmx_successful_request_unchanged(self):
        admin = make_management_user("htmxauth")
        self.client.force_login(admin)
        resp = self.client.get(
            reverse("pattern_form_preview", args=[self.emp.pk]),
            {"effective_from": "2026-01-05", "cycle_weeks": "1", "mode": "change"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("HX-Redirect", resp)

    def test_htmx_request_during_deactivation_redirects_via_login(self):
        """CodeRabbit finding: the deactivation middleware returns 302
        on expired accounts. HTMX must not follow that and swap the
        login page into a fragment. The middleware order in settings.py
        puts HTMXLoginRedirectMiddleware above EmployeeDeactivationMiddleware
        so its response phase wraps the deactivation 302.
        """
        user = make_staff_user("deacthtmx")
        emp = make_employee(email=user.email)
        emp.user = user
        emp.last_day = timezone.localdate() - timedelta(days=1)
        emp.save()
        user.is_active = True
        user.save(update_fields=["is_active"])

        self.client.force_login(user)
        resp = self.client.get(reverse("home"), HTTP_HX_REQUEST="true")
        self.assertEqual(resp.status_code, 204)
        self.assertIn("/accounts/login/", resp["HX-Redirect"])
