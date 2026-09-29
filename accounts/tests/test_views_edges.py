from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from accounts.views import get_client_ip

from .factories import make_employee, make_staff_user, make_superuser

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


class GetClientIpTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_cf_header_wins_over_xff(self):
        req = self.rf.get(
            "/",
            HTTP_CF_CONNECTING_IP="1.2.3.4",
            HTTP_X_FORWARDED_FOR="9.9.9.9",
        )
        self.assertEqual(get_client_ip(req), "1.2.3.4")

    def test_xff_fallback(self):
        req = self.rf.get("/", HTTP_X_FORWARDED_FOR="5.6.7.8, 10.0.0.1")
        self.assertEqual(get_client_ip(req), "5.6.7.8")

    def test_remote_addr_last_resort(self):
        req = self.rf.get("/")
        self.assertEqual(get_client_ip(req), "127.0.0.1")

    def test_cf_header_whitespace_stripped(self):
        req = self.rf.get("/", HTTP_CF_CONNECTING_IP="  1.2.3.4  ")
        self.assertEqual(get_client_ip(req), "1.2.3.4")


@override_settings(CACHES=_LOCMEM_CACHES)
class SignupViewEdgeTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.emp = make_employee(email="new@example.com")

    def test_get_renders_form(self):
        resp = self.client.get(reverse("signup"))
        self.assertEqual(resp.status_code, 200)

    @patch("accounts.otp.send_email")
    def test_rate_limit_hides_form(self, mock_send):
        from accounts import otp as otp_service

        for _ in range(5):
            otp_service.check_signup_rate_limit("127.0.0.1")

        resp = self.client.post(
            reverse("signup"),
            {
                "username": "user",
                "email": self.emp.email,
                "password1": "complexpass123!",
                "password2": "complexpass123!",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context.get("rate_limited"))
        mock_send.assert_not_called()


@override_settings(CACHES=_LOCMEM_CACHES)
class VerifySignupOtpEdgeTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()

    def test_no_session_redirects_to_signup(self):
        resp = self.client.get(reverse("verify_signup_otp"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("signup"))

    def test_with_session_renders(self):
        session = self.client.session
        session["pending_signup"] = {
            "email": "x@example.com",
            "username": "x",
            "password_hash": "fake",
            "employee_id": "00000000-0000-0000-0000-000000000000",
        }
        session.save()
        resp = self.client.get(reverse("verify_signup_otp"))
        self.assertEqual(resp.status_code, 200)

    def test_post_empty_code_shows_error(self):
        session = self.client.session
        session["pending_signup"] = {
            "email": "x@example.com",
            "username": "x",
            "password_hash": "fake",
            "employee_id": "00000000-0000-0000-0000-000000000000",
        }
        session.save()
        resp = self.client.post(reverse("verify_signup_otp"), {"code": ""})
        self.assertEqual(resp.status_code, 200)

    @patch("accounts.otp.send_email")
    def test_resend_action(self, mock_send):
        from accounts import otp as otp_service

        emp = make_employee(email="resend@example.com")
        session = self.client.session
        session["pending_signup"] = {
            "email": emp.email,
            "username": "x",
            "password_hash": "fake",
            "employee_id": str(emp.pk),
        }
        session.save()

        # Prime the OTP (this is what the signup POST would have done)
        otp_service.issue_signup_otp(emp.email)
        mock_send.reset_mock()

        # Immediate resend should hit the cooldown
        self.client.post(
            reverse("verify_signup_otp"),
            {"action": "resend"},
        )
        mock_send.assert_not_called()


@override_settings(CACHES=_LOCMEM_CACHES)
class VerifyOtpEdgeTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.user = make_superuser("otpuser")
        self.client.force_login(self.user)

    def test_no_email_redirects_to_profile(self):
        self.user.email = ""
        self.user.save()
        resp = self.client.get(reverse("verify_otp"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("profile"))

    @patch("accounts.otp.send_email")
    def test_get_issues_otp_when_none_live(self, mock_send):
        self.client.get(reverse("verify_otp"))
        mock_send.assert_called_once()

    @patch("accounts.otp.send_email")
    def test_get_with_live_otp_skips_send(self, mock_send):
        self.client.get(reverse("verify_otp"))
        mock_send.reset_mock()
        self.client.get(reverse("verify_otp"))
        mock_send.assert_not_called()

    @patch("accounts.otp.send_email")
    def test_post_empty_code_shows_error(self, mock_send):
        self.client.get(reverse("verify_otp"))
        resp = self.client.post(reverse("verify_otp"), {"code": ""})
        self.assertEqual(resp.status_code, 200)

    @patch("accounts.otp.send_email")
    def test_post_resend_action(self, mock_send):
        self.client.get(reverse("verify_otp"))
        mock_send.reset_mock()
        # Immediately try resend — should be rate-limited
        self.client.post(reverse("verify_otp"), {"action": "resend"})
        mock_send.assert_not_called()


@override_settings(CACHES=_LOCMEM_CACHES)
class SafeNextTests(TestCase):
    def setUp(self):
        self.user = make_staff_user()
        self.client.force_login(self.user)

    def test_next_used_when_valid(self):
        resp = self.client.post(
            reverse("profile"),
            {
                "username": self.user.username,
                "first_name": "",
                "last_name": "",
            },
        )
        self.assertEqual(resp.status_code, 302)

    def test_external_next_ignored(self):
        # If a `next` param points off-site, fall back to profile
        resp = self.client.get(
            reverse("verify_otp"),
            {"next": "https://evil.example.com/"},
        )
        self.assertEqual(resp.status_code, 200)
        # The rendered context should have a safe next
        self.assertNotEqual(resp.context.get("next"), "https://evil.example.com/")


@override_settings(CACHES=_LOCMEM_CACHES)
class ProfileViewEdgeTests(TestCase):
    def setUp(self):
        self.user = make_staff_user()
        self.client.force_login(self.user)

    def test_post_invalid_rerenders(self):
        User.objects.create_user(username="taken", password="p")
        resp = self.client.post(
            reverse("profile"),
            {"username": "taken", "first_name": "", "last_name": ""},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["form"].errors)

    def test_post_success_redirects(self):
        resp = self.client.post(
            reverse("profile"),
            {"username": "newname", "first_name": "A", "last_name": "B"},
        )
        self.assertEqual(resp.status_code, 302)


@override_settings(CACHES=_LOCMEM_CACHES)
class ApproveAccountEdgeTests(TestCase):
    def setUp(self):
        self.admin = make_superuser("approver")
        self.client.force_login(self.admin)
        emp = make_employee(email="newbie@example.com")
        self.user = User.objects.create_user(
            username="newbie",
            password="p",
            email=emp.email,
            is_active=False,
        )
        emp.user = self.user
        emp.save()

    def test_get_does_not_change_state(self):
        self.client.get(reverse("approve_account", args=[self.user.pk]))
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    @patch("schedule.notifications.send_account_approved_email")
    def test_notify_success(self, mock_send):
        mock_send.return_value = (True, None)
        self.client.post(
            reverse("approve_account", args=[self.user.pk]),
            {"notify": "1"},
        )
        mock_send.assert_called_once()
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    @patch("schedule.notifications.send_account_approved_email")
    def test_notify_failure_still_approves(self, mock_send):
        mock_send.return_value = (False, "no email")
        self.client.post(
            reverse("approve_account", args=[self.user.pk]),
            {"notify": "1"},
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    @patch("schedule.notifications.send_account_approved_email")
    def test_notify_returns_error_still_approves(self, mock_send):
        """If email fails, approval still goes through."""
        mock_send.return_value = (False, "Could not send email.")
        self.client.post(
            reverse("approve_account", args=[self.user.pk]),
            {"notify": "1"},
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
