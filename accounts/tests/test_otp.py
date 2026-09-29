from unittest.mock import patch

from django.test import TestCase, override_settings

from accounts import otp as otp_service

from .factories import make_staff_user

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


@override_settings(CACHES=_LOCMEM_CACHES)
class OtpServiceTests(TestCase):
    def setUp(self):
        # Clear cache between tests
        from django.core.cache import cache

        cache.clear()
        self.user = make_staff_user()

    # ----- password-change OTP (keyed by user.id) -----

    @patch("accounts.otp.send_email")
    @patch("accounts.otp._generate", return_value="123456")
    def test_issue_and_verify(self, mock_gen, mock_send):
        self.assertTrue(otp_service.issue_otp(self.user))
        self.assertTrue(otp_service.verify_otp(self.user, "123456"))
        self.assertFalse(otp_service.verify_otp(self.user, "654321"))

    @patch("accounts.otp.send_email")
    @patch("accounts.otp._generate", return_value="123456")
    def test_clear_invalidates(self, mock_gen, mock_send):
        otp_service.issue_otp(self.user)
        otp_service.clear(self.user)
        self.assertFalse(otp_service.verify_otp(self.user, "123456"))

    @patch("accounts.otp.send_email")
    @patch("accounts.otp._generate", return_value="123456")
    def test_three_wrong_attempts_invalidate(self, mock_gen, mock_send):
        otp_service.issue_otp(self.user)
        otp_service.record_failed_attempt(self.user)
        otp_service.record_failed_attempt(self.user)
        remaining = otp_service.record_failed_attempt(self.user)
        self.assertEqual(remaining, 0)
        # OTP is cleared on lockout
        self.assertFalse(otp_service.verify_otp(self.user, "123456"))

    def test_no_email_returns_false(self):
        self.user.email = ""
        self.user.save()
        self.assertFalse(otp_service.issue_otp(self.user))

    @patch("accounts.otp.send_email")
    @patch("accounts.otp._generate", return_value="123456")
    def test_verify_strips_whitespace(self, mock_gen, mock_send):
        otp_service.issue_otp(self.user)
        self.assertTrue(otp_service.verify_otp(self.user, " 123456 "))

    # ----- rate limiting -----

    @patch("accounts.otp.send_email")
    @patch("accounts.otp._generate", return_value="123456")
    def test_first_send_allowed(self, mock_gen, mock_send):
        can, wait = otp_service.send_status(self.user.id)
        self.assertTrue(can)
        otp_service.issue_otp(self.user)

    @patch("accounts.otp.send_email")
    @patch("accounts.otp._generate", return_value="123456")
    def test_second_send_blocked_within_cooldown(self, mock_gen, mock_send):
        otp_service.issue_otp(self.user)
        can, wait = otp_service.send_status(self.user.id)
        self.assertFalse(can)
        self.assertGreater(wait, 0)

    # ----- signup OTP (keyed by email hash) -----

    @patch("accounts.otp.send_email")
    @patch("accounts.otp._generate", return_value="999999")
    def test_signup_otp_issue_and_verify(self, mock_gen, mock_send):
        otp_service.issue_signup_otp("new@example.com")
        self.assertTrue(otp_service.verify_signup_otp("new@example.com", "999999"))
        self.assertFalse(otp_service.verify_signup_otp("new@example.com", "000000"))

    @patch("accounts.otp.send_email")
    @patch("accounts.otp._generate", return_value="999999")
    def test_signup_otp_case_insensitive_email(self, mock_gen, mock_send):
        otp_service.issue_signup_otp("New@Example.com")
        self.assertTrue(otp_service.verify_signup_otp("new@example.com", "999999"))

    def test_signup_otp_exists_returns_false_when_none(self):
        self.assertFalse(otp_service.signup_otp_exists("never@example.com"))


@override_settings(CACHES=_LOCMEM_CACHES)
class MaskEmailTests(TestCase):
    def test_short_local_part(self):
        self.assertEqual(otp_service.mask_email("ab@x.com"), "a*@x.com")

    def test_long_local_part(self):
        self.assertEqual(otp_service.mask_email("alice@x.com"), "a***e@x.com")

    def test_no_at_sign(self):
        self.assertEqual(otp_service.mask_email("noemail"), "noemail")

    def test_empty(self):
        self.assertEqual(otp_service.mask_email(""), "")


@override_settings(CACHES=_LOCMEM_CACHES)
class SignupRateLimitTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()

    def test_first_attempt_allowed(self):
        self.assertTrue(otp_service.check_signup_rate_limit("1.2.3.4"))

    def test_under_limit_allowed(self):
        for _ in range(4):
            otp_service.check_signup_rate_limit("1.2.3.4")
        self.assertTrue(otp_service.check_signup_rate_limit("1.2.3.4"))

    def test_at_limit_blocked(self):
        for _ in range(5):
            otp_service.check_signup_rate_limit("1.2.3.4")
        self.assertFalse(otp_service.check_signup_rate_limit("1.2.3.4"))

    def test_different_ip_unaffected(self):
        for _ in range(5):
            otp_service.check_signup_rate_limit("1.2.3.4")
        self.assertTrue(otp_service.check_signup_rate_limit("5.6.7.8"))

    def test_empty_ip_allowed(self):
        self.assertTrue(otp_service.check_signup_rate_limit(""))
