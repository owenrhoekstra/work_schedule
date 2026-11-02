from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from .factories import make_staff_user, make_superuser

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


@override_settings(CACHES=_LOCMEM_CACHES)
class OtpGatedPasswordChangeTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.user = make_superuser("admin")
        self.client.force_login(self.user)

    def test_unverified_redirects_to_otp_page(self):
        resp = self.client.get(reverse("password_change"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("verify-otp", resp.url)
        # next param carries the original destination
        self.assertIn(reverse("password_change"), resp.url)

    def test_verify_page_issues_otp(self):
        with patch("accounts.otp.send_email") as mock_send:
            resp = self.client.get(reverse("verify_otp"))
        self.assertEqual(resp.status_code, 200)
        mock_send.assert_called_once()

    @patch("accounts.otp.send_email")
    @patch("accounts.otp._generate", return_value="123456")
    def test_correct_otp_sets_session_and_unlocks(self, mock_gen, mock_send):
        self.client.get(reverse("verify_otp"))
        resp = self.client.post(
            reverse("verify_otp"),
            {"code": "123456", "next": reverse("password_change")},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("otp_verified_at", self.client.session)
        # Password change now reachable
        resp = self.client.get(reverse("password_change"))
        self.assertEqual(resp.status_code, 200)

    @patch("accounts.otp.send_email")
    @patch("accounts.otp._generate", return_value="123456")
    def test_wrong_otp_does_not_unlock(self, mock_gen, mock_send):
        self.client.get(reverse("verify_otp"))
        resp = self.client.post(
            reverse("verify_otp"),
            {"code": "999999", "next": reverse("password_change")},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("otp_verified_at", self.client.session)

    @patch("accounts.otp.send_email")
    @patch("accounts.otp._generate", return_value="123456")
    def test_completing_change_clears_flag(self, mock_gen, mock_send):
        self.client.get(reverse("verify_otp"))
        self.client.post(
            reverse("verify_otp"),
            {"code": "123456", "next": reverse("password_change")},
        )
        # Change password
        resp = self.client.post(
            reverse("password_change"),
            {
                "old_password": "pass",
                "new_password1": "newcomplexpass456!",
                "new_password2": "newcomplexpass456!",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn("otp_verified_at", self.client.session)

    @patch("accounts.otp.send_email")
    @patch("accounts.otp._generate", return_value="123456")
    def test_resend_blocked_within_cooldown(self, mock_gen, mock_send):
        self.client.get(reverse("verify_otp"))  # first send
        initial_count = mock_send.call_count
        # Immediate resend should be blocked
        self.client.post(reverse("verify_otp"), {"action": "resend"})
        self.assertEqual(mock_send.call_count, initial_count)

    def test_no_email_redirects_to_profile(self):
        self.user.email = ""
        self.user.save()
        resp = self.client.get(reverse("verify_otp"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("profile"))


@override_settings(CACHES=_LOCMEM_CACHES)
class AdminPasswordChangeRedirectTests(TestCase):
    """CodeRabbit #2 regression: admin's self-service password change
    is redirected to the OTP-gated /accounts/password_change/ flow.

    Both GET and POST go through the override — the redirect is
    unconditional in _admin_password_change_redirect. Admin's
    admin_view wrapper runs first (auth/staff check) and is intact.

    The follow-the-redirect case is the important one: it verifies the
    redirect chain actually ends at the OTP gate, not just at another
    password change view. Without it, a future refactor that redirects
    admin:password_change to a non-gated target would still pass the
    first two tests.
    """

    def setUp(self):
        self.user = make_superuser("adminpwtest")
        self.client.force_login(self.user)

    def test_get_redirects_to_accounts_password_change(self):
        resp = self.client.get(reverse("admin:password_change"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("password_change"))

    def test_post_redirects_to_accounts_password_change(self):
        # The old-password form is never processed — the redirect
        # fires before PasswordChangeView.form_valid runs.
        resp = self.client.post(
            reverse("admin:password_change"),
            {
                "old_password": "pass",
                "new_password1": "x",
                "new_password2": "x",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("password_change"))

    def test_redirect_target_is_otp_gated(self):
        # Follow the redirect and confirm the OTP gate fires (session
        # has no otp_verified_at, so dispatch redirects to verify_otp).
        resp = self.client.get(reverse("admin:password_change"), follow=False)
        follow = self.client.get(resp.url, follow=False)
        self.assertEqual(follow.status_code, 302)
        self.assertIn(reverse("verify_otp"), follow.url)