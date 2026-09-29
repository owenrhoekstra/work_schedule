from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.forms import SignUpForm  # noqa
from schedule.models import Employee

from .factories import make_employee, make_role

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


@override_settings(CACHES=_LOCMEM_CACHES)
class SignupFlowTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.emp = make_employee(email="new@example.com")

    def _post_signup(self, **overrides):
        data = {
            "username": "newuser",
            "email": self.emp.email,
            "password1": "complexpass123!",
            "password2": "complexpass123!",
        }
        data.update(overrides)
        return self.client.post(reverse("signup"), data)

    @patch("accounts.otp.send_email")
    def test_signup_stashes_session_and_redirects_to_verify(self, mock_send):
        resp = self._post_signup()
        self.assertEqual(resp.status_code, 302)
        self.assertIn("verify-signup-otp", resp.url)
        self.assertIn("pending_signup", self.client.session)
        self.assertEqual(self.client.session["pending_signup"]["email"], self.emp.email)
        mock_send.assert_called_once()
        # No user created yet
        self.assertFalse(User.objects.filter(username="newuser").exists())

    @patch("accounts.otp.send_email")
    def test_signup_with_unknown_email_no_otp_sent(self, mock_send):
        resp = self._post_signup(email="unknown@example.com")
        self.assertEqual(resp.status_code, 200)
        mock_send.assert_not_called()
        self.assertNotIn("pending_signup", self.client.session)

    def test_verify_page_redirects_without_session(self):
        resp = self.client.get(reverse("verify_signup_otp"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("signup"), resp.url)

    @patch("accounts.otp.send_email")
    @patch("accounts.otp._generate", return_value="111111")
    def test_correct_otp_creates_user_and_links(self, mock_gen, mock_send):
        self._post_signup()
        resp = self.client.post(reverse("verify_signup_otp"), {"code": "111111"})
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "registration/signup_pending.html")

        user = User.objects.get(username="newuser")
        self.assertFalse(user.is_active)
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.user_id, user.pk)
        # session cleared
        self.assertNotIn("pending_signup", self.client.session)

    @patch("accounts.otp.send_email")
    @patch("accounts.otp._generate", return_value="111111")
    def test_wrong_otp_does_not_create_user(self, mock_gen, mock_send):
        self._post_signup()
        self.client.post(reverse("verify_signup_otp"), {"code": "999999"})
        self.assertFalse(User.objects.filter(username="newuser").exists())
        self.assertIn("pending_signup", self.client.session)

    @patch("accounts.otp.send_email")
    @patch("accounts.otp._generate", return_value="111111")
    def test_three_wrong_attempts_invalidate_otp(self, mock_gen, mock_send):
        self._post_signup()
        for _ in range(3):
            self.client.post(reverse("verify_signup_otp"), {"code": "999999"})
        # Even the correct code now fails
        self.client.post(reverse("verify_signup_otp"), {"code": "111111"})
        self.assertFalse(User.objects.filter(username="newuser").exists())

    @patch("accounts.otp.send_email")
    @patch("accounts.otp._generate", return_value="111111")
    def test_duplicate_link_protection(self, mock_gen, mock_send):
        """If employee was linked elsewhere, second verify does not clobber."""
        self._post_signup()
        # Simulate another session having completed first
        other = User.objects.create_user(username="otheruser", password="p")
        self.emp.user = other
        self.emp.save()
        resp = self.client.post(reverse("verify_signup_otp"), {"code": "111111"})
        # Should not create a second user; should redirect to login
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(User.objects.filter(username="newuser").exists())


@override_settings(CACHES=_LOCMEM_CACHES)
class SignupRateLimitTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.emp = make_employee(email="new@example.com")

    @patch("accounts.otp.send_email")
    def test_sixth_attempt_rate_limited(self, mock_send):
        data = {
            "username": "newuser",
            "email": self.emp.email,
            "password1": "complexpass123!",
            "password2": "complexpass123!",
        }
        # Five allowed
        for i in range(5):
            self.client.post(reverse("signup"), {**data, "username": f"user{i}"})
        # Sixth is rate-limited — page shows rate_limited context
        resp = self.client.post(reverse("signup"), {**data, "username": "user6"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context.get("rate_limited"))
