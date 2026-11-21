"""Tests for POST /api/v1/schedule/overrides/<employee>/<date>/."""

from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase

from schedule.models import (
    CompanyMembership,
    DayOverride,
    ShiftOverride,
)
from schedule.tests._helpers import login_as
from schedule.tests.factories import (
    make_company,
    make_employee,
    make_management_user,
)

User = get_user_model()


def _make_admin_with_perms(company, username, *perm_codes):
    """Company admin with ONLY the given schedule perms (plus view_shift
    so /me/'s available_scopes returns something — not required by the
    endpoint, but harmless for realism)."""
    user = User.objects.create_user(
        username=username, password="pass", email=f"{username}@x.com"
    )
    for code in perm_codes:
        user.user_permissions.add(Permission.objects.get(codename=code))
    CompanyMembership.objects.create(
        user=user, company=company, role="admin", status="active"
    )
    return user


class OverrideEndpointTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.admin = make_management_user(company=self.company)
        self.employee = make_employee(
            company=self.company, with_pattern=False, email="emp@x.com"
        )
        self.today = date.today()

    def _url(self, employee=None, when=None):
        employee = employee or self.employee
        when = when or self.today
        return f"/api/v1/schedule/overrides/{employee.pk}/{when.isoformat()}/"

    def _post(self, payload, employee=None, when=None):
        return self.client.post(
            self._url(employee, when),
            data=payload,
            content_type="application/json",
        )

    # ---- Auth -----------------------------------------------------------

    def test_anonymous_returns_401(self):
        response = self.client.post(
            self._url(),
            data={"action": "off"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_non_admin_returns_403(self):
        user = User.objects.create_user(
            username="nonadmin", password="pass", email="na@x.com"
        )
        CompanyMembership.objects.create(
            user=user, company=self.company, role="member", status="active"
        )
        user.user_permissions.add(Permission.objects.get(codename="add_shift"))
        login_as(self.client, user, self.company)

        response = self._post({"action": "save", "start": "09:00", "end": "17:00"})
        self.assertEqual(response.status_code, 403)

    # ---- Per-action perms ----------------------------------------------

    def test_add_shift_only_allows_save_denies_off(self):
        user = _make_admin_with_perms(
            self.company, "addonly", "add_shift", "view_shift"
        )
        login_as(self.client, user, self.company)

        save = self._post({"action": "save", "start": "09:00", "end": "17:00"})
        self.assertEqual(save.status_code, 200)

        off = self._post({"action": "off"})
        self.assertEqual(off.status_code, 403)

    def test_delete_shift_only_allows_off_denies_save(self):
        user = _make_admin_with_perms(
            self.company, "delonly", "delete_shift", "view_shift"
        )
        login_as(self.client, user, self.company)

        off = self._post({"action": "off"})
        self.assertEqual(off.status_code, 200)

        save = self._post({"action": "save", "start": "09:00", "end": "17:00"})
        self.assertEqual(save.status_code, 403)

    # ---- Save ----------------------------------------------------------

    def test_save_creates_override_and_returns_updated_row(self):
        login_as(self.client, self.admin, self.company)
        response = self._post({"action": "save", "start": "09:00", "end": "17:00"})
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Cell at this date is now an override.
        cell = next(
            c for c in data["employee"]["cells"] if c["date"] == self.today.isoformat()
        )
        self.assertEqual(cell["kind"], "override")
        self.assertEqual(cell["start"], "09:00")
        self.assertEqual(cell["end"], "17:00")
        self.assertTrue(cell["has_override"])

        self.assertTrue(
            ShiftOverride.objects.filter(
                employee=self.employee, date=self.today
            ).exists()
        )

    def test_save_rejects_invalid_time_format(self):
        login_as(self.client, self.admin, self.company)
        response = self._post({"action": "save", "start": "not-a-time", "end": "17:00"})
        self.assertEqual(response.status_code, 422)

    def test_save_rejects_end_before_start(self):
        login_as(self.client, self.admin, self.company)
        response = self._post({"action": "save", "start": "17:00", "end": "09:00"})
        self.assertEqual(response.status_code, 422)

    def test_save_rejects_missing_end(self):
        login_as(self.client, self.admin, self.company)
        response = self._post({"action": "save", "start": "09:00"})
        self.assertEqual(response.status_code, 422)

    # ---- Off / Reset ---------------------------------------------------

    def test_off_creates_is_off_override(self):
        login_as(self.client, self.admin, self.company)
        response = self._post({"action": "off"})
        self.assertEqual(response.status_code, 200)
        data = response.json()

        cell = next(
            c for c in data["employee"]["cells"] if c["date"] == self.today.isoformat()
        )
        self.assertEqual(cell["kind"], "off_override")

    def test_reset_deletes_override(self):
        ShiftOverride.objects.create(
            employee=self.employee,
            date=self.today,
            start_time="09:00",
            end_time="17:00",
        )
        login_as(self.client, self.admin, self.company)
        response = self._post({"action": "reset"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            ShiftOverride.objects.filter(
                employee=self.employee, date=self.today
            ).exists()
        )

    def test_reset_on_no_override_is_idempotent(self):
        login_as(self.client, self.admin, self.company)
        response = self._post({"action": "reset"})
        self.assertEqual(response.status_code, 200)

    # ---- Validation gates ----------------------------------------------

    def test_day_override_blocks_mutation(self):
        DayOverride.objects.create(
            company=self.company, date=self.today, status="closed"
        )
        login_as(self.client, self.admin, self.company)
        response = self._post({"action": "off"})
        self.assertEqual(response.status_code, 422)
        self.assertIn("Closed", response.json()["detail"])

    def test_employee_not_yet_started_returns_422(self):
        future_start = self.today + timedelta(days=30)
        emp = make_employee(
            company=self.company,
            with_pattern=False,
            email="future@x.com",
            start_date=future_start,
        )
        login_as(self.client, self.admin, self.company)
        response = self._post({"action": "off"}, employee=emp, when=self.today)
        self.assertEqual(response.status_code, 422)

    def test_unknown_employee_returns_404(self):
        from uuid import uuid4

        login_as(self.client, self.admin, self.company)
        response = self.client.post(
            f"/api/v1/schedule/overrides/{uuid4()}/{self.today.isoformat()}/",
            data={"action": "off"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_invalid_date_returns_400(self):
        login_as(self.client, self.admin, self.company)
        response = self.client.post(
            f"/api/v1/schedule/overrides/{self.employee.pk}/not-a-date/",
            data={"action": "off"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_unknown_action_returns_422(self):
        login_as(self.client, self.admin, self.company)
        response = self._post({"action": "bogus"})
        self.assertEqual(response.status_code, 422)

    # ---- Notifications -------------------------------------------------

    @patch("schedule.services.notifications.send_shift_changes_email")
    def test_notify_true_sends_email(self, mock_send):
        mock_send.return_value = (True, None)
        login_as(self.client, self.admin, self.company)
        response = self._post(
            {"action": "save", "start": "09:00", "end": "17:00", "notify": True}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["notification_sent"])
        self.assertIsNone(data["notification_error"])
        mock_send.assert_called_once()

    @patch("schedule.services.notifications.send_shift_changes_email")
    def test_notify_true_no_change_skips_email(self, mock_send):
        # Pre-create identical override so "save" produces no delta.
        ShiftOverride.objects.create(
            employee=self.employee,
            date=self.today,
            start_time="09:00",
            end_time="17:00",
        )
        login_as(self.client, self.admin, self.company)
        response = self._post(
            {"action": "save", "start": "09:00", "end": "17:00", "notify": True}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["notification_sent"])
        self.assertIsNone(data["notification_error"])
        mock_send.assert_not_called()

    @patch("schedule.services.notifications.send_shift_changes_email")
    def test_notify_true_email_fails_row_still_saved(self, mock_send):
        mock_send.return_value = (False, "SMTP down")
        login_as(self.client, self.admin, self.company)
        response = self._post(
            {"action": "save", "start": "09:00", "end": "17:00", "notify": True}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["notification_sent"])
        self.assertEqual(data["notification_error"], "SMTP down")
        # Row persisted despite notification failure.
        self.assertTrue(
            ShiftOverride.objects.filter(
                employee=self.employee, date=self.today
            ).exists()
        )

    # ---- Shape ---------------------------------------------------------

    def test_response_row_matches_week_endpoint_shape(self):
        login_as(self.client, self.admin, self.company)
        response = self._post({"action": "save", "start": "09:00", "end": "17:00"})
        data = response.json()
        row = data["employee"]
        for key in (
            "id",
            "first_name",
            "last_name",
            "display_name",
            "role_id",
            "role_name",
            "last_day",
            "cycle",
            "cells",
            "total_minutes",
        ):
            self.assertIn(key, row)
        # Every cell carries the default_* fields.
        for cell in row["cells"]:
            self.assertIn("default_start", cell)
            self.assertIn("default_end", cell)
