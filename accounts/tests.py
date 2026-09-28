from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from schedule.models import Employee, Role

_LOCMEM_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}


def make_role(name="Staff", order=10):
    return Role.objects.create(name=name, display_order=order)


def make_employee(email="test@example.com", **kwargs):
    return Employee.objects.create(
        first_name="Test",
        last_name="User",
        email=email,
        role=make_role(),
        start_date=date.today(),
        **kwargs,
    )


def make_superuser(username="admin"):
    return User.objects.create_superuser(
        username=username, password="pass", email=f"{username}@example.com"
    )


@override_settings(CACHES=_LOCMEM_CACHES)
class LoginTests(TestCase):
    def setUp(self):
        self.user = make_superuser()

    def test_login_with_valid_credentials(self):
        resp = self.client.post(
            reverse("login"),
            {"username": self.user.username, "password": "pass"},
        )
        self.assertEqual(resp.status_code, 302)

    def test_login_with_wrong_password_does_not_authenticate(self):
        resp = self.client.post(
            reverse("login"),
            {"username": self.user.username, "password": "wrong"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.wsgi_request.user.is_authenticated)


@override_settings(CACHES=_LOCMEM_CACHES)
class SignupFlowTests(TestCase):
    def setUp(self):
        self.emp = make_employee(email="new@example.com")

    def test_signup_with_valid_email_stashes_pending_and_sends_otp(self):
        with patch("accounts.otp.send_email") as mock_send:
            resp = self.client.post(
                reverse("signup"),
                {
                    "username": "newuser",
                    "email": self.emp.email,
                    "password1": "hunter2hunter2!",
                    "password2": "hunter2hunter2!",
                },
            )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("verify-signup-otp", resp.url)
        self.assertIn("pending_signup", self.client.session)
        mock_send.assert_called_once()
        # No User yet — created only after OTP verification
        self.assertFalse(User.objects.filter(username="newuser").exists())

    def test_signup_with_unknown_email_blocked(self):
        with patch("accounts.otp.send_email") as mock_send:
            resp = self.client.post(
                reverse("signup"),
                {
                    "username": "newuser",
                    "email": "unknown@example.com",
                    "password1": "hunter2hunter2!",
                    "password2": "hunter2hunter2!",
                },
            )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(username="newuser").exists())
        mock_send.assert_not_called()

    def test_otp_verification_creates_user_and_links_employee(self):
        with (
            patch("accounts.otp.send_email"),
            patch("accounts.otp._generate", return_value="123456"),
        ):
            self.client.post(
                reverse("signup"),
                {
                    "username": "newuser",
                    "email": self.emp.email,
                    "password1": "hunter2hunter2!",
                    "password2": "hunter2hunter2!",
                },
            )
            resp = self.client.post(
                reverse("verify_signup_otp"),
                {"code": "123456"},
            )
        self.assertEqual(resp.status_code, 200)
        user = User.objects.get(username="newuser")
        self.assertFalse(user.is_active)  # pending approval
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.user, user)
        # Name was pulled from the Employee record
        self.assertEqual(user.first_name, self.emp.first_name)
        self.assertEqual(user.last_name, self.emp.last_name)


@override_settings(CACHES=_LOCMEM_CACHES)
class PasswordChangeOTPTests(TestCase):
    def setUp(self):
        self.user = make_superuser()

    def test_password_change_redirects_to_otp_when_not_verified(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("password_change"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("verify-otp", resp.url)

    def test_verify_otp_unlocks_password_change(self):
        self.client.force_login(self.user)
        with (
            patch("accounts.otp.send_email"),
            patch("accounts.otp._generate", return_value="654321"),
        ):
            self.client.get(reverse("verify_otp"))
            resp = self.client.post(
                reverse("verify_otp"),
                {
                    "code": "654321",
                    "next": reverse("password_change"),
                },
            )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("otp_verified_at", self.client.session)
        # Password change page now reachable
        resp = self.client.get(reverse("password_change"))
        self.assertEqual(resp.status_code, 200)

    def test_wrong_otp_does_not_unlock(self):
        self.client.force_login(self.user)
        with (
            patch("accounts.otp.send_email"),
            patch("accounts.otp._generate", return_value="111111"),
        ):
            self.client.get(reverse("verify_otp"))
            resp = self.client.post(
                reverse("verify_otp"),
                {"code": "999999", "next": reverse("password_change")},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("otp_verified_at", self.client.session)


@override_settings(CACHES=_LOCMEM_CACHES)
class ProfileViewTests(TestCase):
    def setUp(self):
        self.user = make_superuser()
        self.client.force_login(self.user)

    def test_profile_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("profile"))
        self.assertEqual(resp.status_code, 302)

    def test_profile_renders(self):
        self.assertEqual(self.client.get(reverse("profile")).status_code, 200)

    def test_profile_updates_username(self):
        resp = self.client.post(
            reverse("profile"),
            {
                "username": "renamed",
                "first_name": "New",
                "last_name": "Name",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "renamed")

    def test_profile_rejects_duplicate_username(self):
        User.objects.create_user(username="taken", password="p")
        resp = self.client.post(
            reverse("profile"),
            {"username": "taken", "first_name": "", "last_name": ""},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["form"].errors)
