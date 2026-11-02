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


@override_settings(CACHES=_LOCMEM_CACHES)
class StalePendingSignupTests(TestCase):
    """CodeRabbit #1 regression: pending_signup is rejected when the
    employee changes state between signup start and OTP verification.

    Covers: email change, deactivation, and pre-linked user. Both the
    verify path (mock verify_signup_otp → True) and the resend path.
    Resend must NOT call send_email for a stale session — the check
    runs before otp_service.issue_signup_otp fires.

    Assertions per case:
    - redirect to signup (except already-linked, which redirects to
      login — preserves the pre-fix behavior for that branch)
    - pending_signup cleared from session
    - no User created (verify path)
    - employee.user_id stays unset (email-change / deactivation)
    - resend path: send_email not called
    """

    def setUp(self):
        from django.core.cache import cache

        cache.clear()

    def _prime_session(self, emp):
        session = self.client.session
        session["pending_signup"] = {
            "username": "stale",
            "email": emp.email,
            "password_hash": "fake-hash",
            "employee_id": str(emp.pk),
        }
        session.save()
        return emp

    # ----- verify path -----

    @patch("accounts.otp.verify_signup_otp", return_value=True)
    def test_email_change_rejects_verification(self, mock_verify):
        emp = make_employee(email="original@example.com")
        self._prime_session(emp)
        emp.email = "changed@example.com"
        emp.save(update_fields=["email"])

        resp = self.client.post(
            reverse("verify_signup_otp"), {"code": "123456"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("signup"))
        self.assertNotIn("pending_signup", self.client.session)
        emp.refresh_from_db()
        self.assertIsNone(emp.user_id)
        self.assertFalse(User.objects.filter(username="stale").exists())

    @patch("accounts.otp.verify_signup_otp", return_value=True)
    def test_inactive_employee_rejects_verification(self, mock_verify):
        emp = make_employee(email="active@example.com")
        self._prime_session(emp)
        emp.is_active = False
        emp.save(update_fields=["is_active"])

        resp = self.client.post(
            reverse("verify_signup_otp"), {"code": "123456"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("signup"))
        self.assertNotIn("pending_signup", self.client.session)
        emp.refresh_from_db()
        self.assertIsNone(emp.user_id)
        self.assertFalse(User.objects.filter(username="stale").exists())

    @patch("accounts.otp.verify_signup_otp", return_value=True)
    def test_already_linked_employee_redirects_to_login(self, mock_verify):
        # Existing branch (not new): the user was linked between signup
        # start and verification. Preserves the pre-fix behavior —
        # redirect to login, not signup.
        emp = make_employee(email="linked@example.com")
        other = User.objects.create_user(username="preclaimed", password="p")
        emp.user = other
        emp.save(update_fields=["user"])
        self._prime_session(emp)

        resp = self.client.post(
            reverse("verify_signup_otp"), {"code": "123456"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("login"))
        self.assertNotIn("pending_signup", self.client.session)

    # ----- resend path -----

    @patch("accounts.otp.send_email")
    def test_email_change_rejects_resend(self, mock_send):
        emp = make_employee(email="orig2@example.com")
        self._prime_session(emp)
        emp.email = "new2@example.com"
        emp.save(update_fields=["email"])

        resp = self.client.post(
            reverse("verify_signup_otp"), {"action": "resend"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("signup"))
        self.assertNotIn("pending_signup", self.client.session)
        mock_send.assert_not_called()

    @patch("accounts.otp.send_email")
    def test_inactive_employee_rejects_resend(self, mock_send):
        emp = make_employee(email="act2@example.com")
        self._prime_session(emp)
        emp.is_active = False
        emp.save(update_fields=["is_active"])

        resp = self.client.post(
            reverse("verify_signup_otp"), {"action": "resend"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("signup"))
        self.assertNotIn("pending_signup", self.client.session)
        mock_send.assert_not_called()

    @patch("accounts.otp.send_email")
    def test_already_linked_employee_rejects_resend(self, mock_send):
        emp = make_employee(email="linked2@example.com")
        other = User.objects.create_user(username="preclaimed2", password="p")
        emp.user = other
        emp.save(update_fields=["user"])
        self._prime_session(emp)

        resp = self.client.post(
            reverse("verify_signup_otp"), {"action": "resend"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("signup"))
        self.assertNotIn("pending_signup", self.client.session)
        mock_send.assert_not_called()