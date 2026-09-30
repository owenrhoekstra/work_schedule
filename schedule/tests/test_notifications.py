from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from schedule import notifications

from .factories import make_employee, make_staff_user

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


@override_settings(CACHES=_LOCMEM_CACHES)
class CooldownTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()

    def test_first_call_returns_true(self):
        self.assertTrue(notifications._cooldown_ok("key1"))

    def test_second_call_within_window_returns_false(self):
        notifications._cooldown_ok("key2")
        self.assertFalse(notifications._cooldown_ok("key2"))

    def test_different_keys_independent(self):
        notifications._cooldown_ok("key3a")
        self.assertTrue(notifications._cooldown_ok("key3b"))


@override_settings(CACHES=_LOCMEM_CACHES)
class EmailEligibilityTests(TestCase):
    """Rules that decide whether a schedule email can be sent.

    Welcome and signup OTP are exempt; everything else requires a linked,
    active User and a current employment window.
    """

    def setUp(self):
        from django.core.cache import cache

        cache.clear()

    # ----- shift changes -----

    @patch("schedule.notifications.send_email")
    def test_shift_email_skipped_when_no_user(self, mock_send):
        emp = make_employee()
        changes = [{"label": "Monday", "old": "9:00 AM", "new": "10:00 AM"}]
        ok, err = notifications.send_shift_changes_email(emp, changes, kind="default")
        self.assertFalse(ok)
        self.assertIn("sign", err.lower())
        mock_send.assert_not_called()

    @patch("schedule.notifications.send_email")
    def test_shift_email_skipped_when_user_inactive(self, mock_send):
        user = make_staff_user("inactive")
        user.is_active = False
        user.save()
        emp = make_employee(email=user.email)
        emp.user = user
        emp.save()
        changes = [{"label": "Monday", "old": "9:00 AM", "new": "10:00 AM"}]
        ok, err = notifications.send_shift_changes_email(emp, changes, kind="default")
        self.assertFalse(ok)
        mock_send.assert_not_called()

    @patch("schedule.notifications.send_email")
    def test_shift_email_skipped_when_last_day_past(self, mock_send):
        user = make_staff_user("left")
        emp = make_employee(email=user.email)
        emp.user = user
        emp.last_day = timezone.localdate() - timedelta(days=1)
        emp.save()
        changes = [{"label": "Monday", "old": "9:00 AM", "new": "10:00 AM"}]
        ok, err = notifications.send_shift_changes_email(emp, changes, kind="default")
        self.assertFalse(ok)
        mock_send.assert_not_called()

    @patch("schedule.notifications.send_email")
    def test_shift_email_sent_when_eligible(self, mock_send):
        user = make_staff_user("active")
        emp = make_employee(email=user.email)
        emp.user = user
        emp.save()
        changes = [{"label": "Monday", "old": "9:00 AM", "new": "10:00 AM"}]
        ok, err = notifications.send_shift_changes_email(emp, changes, kind="default")
        self.assertTrue(ok)
        mock_send.assert_called_once()

    @patch("schedule.notifications.send_email")
    def test_shift_email_sent_when_last_day_in_future(self, mock_send):
        user = make_staff_user("scheduled")
        emp = make_employee(email=user.email)
        emp.user = user
        emp.last_day = timezone.localdate() + timedelta(days=14)
        emp.save()
        changes = [{"label": "Monday", "old": "9:00 AM", "new": "10:00 AM"}]
        ok, err = notifications.send_shift_changes_email(emp, changes, kind="default")
        self.assertTrue(ok)
        mock_send.assert_called_once()

    # ----- deactivation -----

    @patch("schedule.notifications.send_email")
    def test_deactivation_email_skipped_without_user(self, mock_send):
        emp = make_employee()
        emp.last_day = timezone.localdate()
        emp.save()
        ok, err = notifications.send_deactivation_email(emp)
        self.assertFalse(ok)
        mock_send.assert_not_called()

    @patch("schedule.notifications.send_email")
    def test_deactivation_email_sent_on_last_day(self, mock_send):
        user = make_staff_user("leaving")
        emp = make_employee(email=user.email)
        emp.user = user
        emp.last_day = timezone.localdate()
        emp.save()
        ok, err = notifications.send_deactivation_email(emp)
        self.assertTrue(ok)
        mock_send.assert_called_once()

    @patch("schedule.notifications.send_email")
    def test_deactivation_email_skipped_after_last_day(self, mock_send):
        user = make_staff_user("gone")
        emp = make_employee(email=user.email)
        emp.user = user
        emp.last_day = timezone.localdate() - timedelta(days=1)
        emp.save()
        ok, err = notifications.send_deactivation_email(emp)
        self.assertFalse(ok)
        mock_send.assert_not_called()

    # ----- account approved -----

    @patch("schedule.notifications.send_email")
    def test_account_approved_skipped_when_employee_departed(self, mock_send):
        user = make_staff_user("pendingapproval")
        emp = make_employee(email=user.email)
        emp.user = user
        emp.last_day = timezone.localdate() - timedelta(days=1)
        emp.save()
        ok, err = notifications.send_account_approved_email(user, emp)
        self.assertFalse(ok)
        mock_send.assert_not_called()

    @patch("schedule.notifications.send_email")
    def test_account_approved_sent_when_employee_active(self, mock_send):
        user = make_staff_user("approveme")
        emp = make_employee(email=user.email)
        emp.user = user
        emp.save()
        ok, err = notifications.send_account_approved_email(user, emp)
        self.assertTrue(ok)
        mock_send.assert_called_once()

    # ----- welcome: exempt from eligibility -----

    @patch("schedule.notifications.send_email")
    def test_welcome_email_sent_without_user(self, mock_send):
        emp = make_employee()
        ok, err = notifications.send_welcome_email(emp)
        self.assertTrue(ok)
        mock_send.assert_called_once()

    @patch("schedule.notifications.send_email")
    def test_welcome_email_sent_even_if_user_inactive(self, mock_send):
        user = make_staff_user("welcomepending")
        user.is_active = False
        user.save()
        emp = make_employee(email=user.email)
        emp.user = user
        emp.save()
        ok, err = notifications.send_welcome_email(emp)
        self.assertTrue(ok)
        mock_send.assert_called_once()


@override_settings(CACHES=_LOCMEM_CACHES)
class WelcomeEmailTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.emp = make_employee()

    @patch("schedule.notifications.send_email")
    def test_sends_with_correct_context(self, mock_send):
        ok, err = notifications.send_welcome_email(self.emp)
        self.assertTrue(ok)
        self.assertIsNone(err)
        mock_send.assert_called_once()
        ctx = mock_send.call_args[1]["context"]
        self.assertEqual(ctx["employee_name"], self.emp.first_name)
        self.assertEqual(ctx["employee_email"], self.emp.email)
        self.assertIn("signup", ctx["signup_url"])
        self.assertEqual(mock_send.call_args[1]["to"], self.emp.email)

    @patch("schedule.notifications.send_email")
    def test_second_send_blocked_by_cooldown(self, mock_send):
        notifications.send_welcome_email(self.emp)
        mock_send.reset_mock()
        ok, err = notifications.send_welcome_email(self.emp)
        self.assertFalse(ok)
        self.assertIn("minute", err.lower())
        mock_send.assert_not_called()

    @patch(
        "schedule.notifications.send_email",
        side_effect=Exception("boom"),
    )
    def test_send_failure_returns_error(self, mock_send):
        ok, err = notifications.send_welcome_email(self.emp)
        self.assertFalse(ok)
        self.assertIn("try again", err.lower())


@override_settings(CACHES=_LOCMEM_CACHES)
class AccountApprovedEmailTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.user = make_staff_user("approved")
        self.emp = make_employee(email=self.user.email)
        self.emp.user = self.user
        self.emp.save()

    @patch("schedule.notifications.send_email")
    def test_sends_with_employee_email(self, mock_send):
        ok, err = notifications.send_account_approved_email(self.user, self.emp)
        self.assertTrue(ok)
        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args[1]["to"], self.emp.email)
        ctx = mock_send.call_args[1]["context"]
        self.assertEqual(ctx["employee_name"], self.emp.first_name)
        self.assertIn("login", ctx["login_url"])

    @patch("schedule.notifications.send_email")
    def test_falls_back_to_user_email_when_no_employee(self, mock_send):
        ok, err = notifications.send_account_approved_email(self.user, None)
        self.assertTrue(ok)
        self.assertEqual(mock_send.call_args[1]["to"], self.user.email)

    @patch("schedule.notifications.send_email")
    def test_returns_error_when_no_email_anywhere(self, mock_send):
        self.user.email = ""
        self.user.save()
        ok, err = notifications.send_account_approved_email(self.user, None)
        self.assertFalse(ok)
        self.assertIn("No email", err)
        mock_send.assert_not_called()

    @patch("schedule.notifications.send_email")
    def test_cooldown(self, mock_send):
        notifications.send_account_approved_email(self.user, self.emp)
        mock_send.reset_mock()
        ok, err = notifications.send_account_approved_email(self.user, self.emp)
        self.assertFalse(ok)
        mock_send.assert_not_called()


@override_settings(CACHES=_LOCMEM_CACHES)
class ShiftChangesEmailTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        # Notifications are gated on a linked, active user — build one.
        self.user = make_staff_user("shiftuser")
        self.emp = make_employee(email=self.user.email)
        self.emp.user = self.user
        self.emp.save()

    @patch("schedule.notifications.send_email")
    def test_override_single_change(self, mock_send):
        changes = [{"label": "Monday, Oct 5", "old": "9:00 AM", "new": "10:00 AM"}]
        ok, err = notifications.send_shift_changes_email(
            self.emp, changes, kind="override"
        )
        self.assertTrue(ok)
        ctx = mock_send.call_args[1]["context"]
        self.assertIn("Monday, Oct 5", ctx["headline"])
        self.assertEqual(ctx["changes"], changes)

    @patch("schedule.notifications.send_email")
    def test_override_multi_change(self, mock_send):
        changes = [
            {"label": "Monday", "old": "9:00 AM", "new": "10:00 AM"},
            {"label": "Tuesday", "old": "9:00 AM", "new": "OFF"},
        ]
        notifications.send_shift_changes_email(self.emp, changes, kind="override")
        ctx = mock_send.call_args[1]["context"]
        self.assertIn("shift schedule", ctx["headline"].lower())

    @patch("schedule.notifications.send_email")
    def test_default_change(self, mock_send):
        changes = [{"label": "Monday", "old": "9:00 AM", "new": "10:00 AM"}]
        notifications.send_shift_changes_email(self.emp, changes, kind="default")
        ctx = mock_send.call_args[1]["context"]
        self.assertIn("regular hours", ctx["headline"].lower())

    @patch("schedule.notifications.send_email")
    def test_cycle_extended(self, mock_send):
        cycle_change = {
            "old_cycle": 1,
            "new_cycle": 2,
            "new_weeks": [
                {"label": "Week B", "rows": [{"day": "Monday", "time": "OFF"}]}
            ],
        }
        notifications.send_shift_changes_email(
            self.emp, [], kind="default", cycle_change=cycle_change
        )
        ctx = mock_send.call_args[1]["context"]
        self.assertIn("extended", ctx["headline"].lower())

    @patch("schedule.notifications.send_email")
    def test_cycle_shortened(self, mock_send):
        cycle_change = {
            "old_cycle": 3,
            "new_cycle": 2,
            "new_weeks": [],
        }
        notifications.send_shift_changes_email(
            self.emp, [], kind="default", cycle_change=cycle_change
        )
        ctx = mock_send.call_args[1]["context"]
        self.assertIn("shortened", ctx["headline"].lower())

    @patch("schedule.notifications.send_email")
    def test_no_changes_no_send(self, mock_send):
        ok, err = notifications.send_shift_changes_email(self.emp, [], kind="default")
        self.assertFalse(ok)
        mock_send.assert_not_called()


@override_settings(CACHES=_LOCMEM_CACHES)
class DeactivationEmailTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        # Deactivation emails go out while the employee is still on the
        # schedule, so use a future last_day and a linked user.
        self.user = make_staff_user("deactuser")
        self.emp = make_employee(email=self.user.email)
        self.emp.user = self.user
        self.emp.last_day = timezone.localdate() + timedelta(days=14)
        self.emp.save()

    @patch("schedule.notifications.send_email")
    def test_sends_with_last_day(self, mock_send):
        notifications.send_deactivation_email(self.emp)
        mock_send.assert_called_once()
        ctx = mock_send.call_args[1]["context"]
        self.assertEqual(ctx["employee_name"], self.emp.first_name)
        self.assertEqual(ctx["last_day"], self.emp.last_day)

    @patch("schedule.notifications.send_email")
    def test_includes_reason_when_provided(self, mock_send):
        notifications.send_deactivation_email(self.emp, reason="Thanks for everything.")
        ctx = mock_send.call_args[1]["context"]
        self.assertEqual(ctx["reason"], "Thanks for everything.")

    @patch(
        "schedule.notifications.send_email",
        side_effect=Exception("boom"),
    )
    def test_send_failure_returns_error(self, mock_send):
        ok, err = notifications.send_deactivation_email(self.emp)
        self.assertFalse(ok)
        self.assertIn("try again", err.lower())
