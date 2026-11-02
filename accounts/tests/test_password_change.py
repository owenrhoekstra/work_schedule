from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

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
    """CodeRabbit #2 regression: both admin password-change surfaces
    route through the OTP gate.

    Two distinct entry points, both covered here:

    1. /admin/password_change/ (AdminSite.password_change)
       - self-service entry. Django's default handler is a pure
         redirect to the per-user route below. Our override swaps
         that redirect for accounts:password_change (the OTP-gated
         accounts view) — canonical branded form, one hop.

    2. /admin/auth/user/<id>/password/ (UserAdmin.user_change_password)
       - the actual form. Handles self-change AND other-user reset.
         Reachable directly (typed URL, bookmark) so the
         password_change redirect alone is insufficient. Our override
         swaps the URL for a wrapper that checks `otp_verified_at`
         before delegating to `user_change_password`.

    The two OTP gates work the same way: without a fresh
    `otp_verified_at` session flag, redirect to `verify_otp?next=...`.
    After OTP, the user lands back here, the flag is present, the
    wrapper delegates, and Django's normal form rendering runs.
    """

    def setUp(self):
        self.user = make_superuser("adminpwtest")
        self.client.force_login(self.user)

    # ----- /admin/password_change/ (self-service entry point) -----

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
        # has no otp_verified_at, so OTPGatedPasswordChangeView.dispatch
        # redirects to verify_otp).
        resp = self.client.get(reverse("admin:password_change"), follow=False)
        follow = self.client.get(resp.url, follow=False)
        self.assertEqual(follow.status_code, 302)
        self.assertIn(reverse("verify_otp"), follow.url)

    # ----- /admin/auth/user/<id>/password/ (per-user form) -----

    def test_user_admin_password_change_redirects_to_otp(self):
        """UserAdmin's per-user route redirects to the OTP gate.

        Distinct from /admin/password_change/ — this is the actual
        form URL, reachable directly. Before the fix, hitting it with
        no OTP rendered the form; now it short-circuits to verify_otp.
        """
        target = make_staff_user("targetpw")
        url = reverse("admin:auth_user_password_change", args=[target.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("verify_otp"), resp.url)
        # next preserves the target so the post-OTP redirect lands back here
        self.assertIn(url, resp.url)

    def test_user_admin_password_change_post_redirects_to_otp(self):
        # POST also short-circuits before AdminPasswordChangeForm runs.
        target = make_staff_user("targetpw2")
        url = reverse("admin:auth_user_password_change", args=[target.pk])
        resp = self.client.post(url, {"password1": "x", "password2": "x"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("verify_otp"), resp.url)

    def test_user_admin_password_change_renders_after_otp(self):
        """After OTP, UserAdmin's form renders normally.

        Proves the wrapper delegates correctly to user_change_password
        once the session flag is set. Superuser passes
        has_change_permission, so no 403 — the delegation is what's
        being tested, not the authz (that's existing Django behavior,
        unchanged by the override).
        """
        target = make_staff_user("targetpw3")
        session = self.client.session
        session["otp_verified_at"] = timezone.now().isoformat()
        session.save()

        url = reverse("admin:auth_user_password_change", args=[target.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_user_admin_password_change_self_redirects_to_otp(self):
        """Self-change via the per-user URL is also gated.

        The admin typing their own per-user URL should not bypass OTP
        just because it's the same person. Distinct from
        admin:password_change, which only covers the self-service
        entry point.
        """
        url = reverse(
            "admin:auth_user_password_change", args=[self.user.pk]
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("verify_otp"), resp.url)