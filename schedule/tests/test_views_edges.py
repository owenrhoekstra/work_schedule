from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from schedule.models import Employee, Role, Shift, ShiftOverride, Title

from .factories import (
    make_employee,
    make_manager_user,
    make_role,
    make_staff_user,
    make_superuser,
)

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


@override_settings(CACHES=_LOCMEM_CACHES)
class AddEmployeeViewTests(TestCase):
    def setUp(self):
        self.admin = make_superuser()
        self.client.force_login(self.admin)
        self.role = make_role("Receptionist", order=20)

    def form_data(self, **overrides):
        data = {
            "title": "",
            "first_name": "New",
            "last_name": "Hire",
            "role": str(self.role.pk),
            "email": "newhire@example.com",
            "start_date": "2026-10-01",
        }
        data.update(overrides)
        return data

    def test_post_creates_and_redirects(self):
        resp = self.client.post(reverse("add_employee"), self.form_data())
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Employee.objects.filter(email="newhire@example.com").exists())

    def test_post_links_unlinked_user(self):
        user = make_staff_user("existing")
        user.email = "match@example.com"
        user.save()
        self.client.post(
            reverse("add_employee"), self.form_data(email="match@example.com")
        )
        emp = Employee.objects.get(email="match@example.com")
        self.assertEqual(emp.user_id, user.pk)

    def test_post_does_not_steal_linked_user(self):
        user = make_staff_user("linked")
        user.email = "taken@example.com"
        user.save()
        other = make_employee(email="other@example.com")
        other.user = user
        other.save()
        self.client.post(
            reverse("add_employee"), self.form_data(email="taken@example.com")
        )
        new_emp = Employee.objects.get(email="taken@example.com")
        self.assertIsNone(new_emp.user_id)

    @patch("schedule.notifications.send_email")
    def test_post_with_notify_sends_welcome(self, mock_send):
        self.client.post(
            reverse("add_employee"),
            {**self.form_data(), "notify": "1"},
        )
        mock_send.assert_called_once()

    @patch("schedule.notifications.send_email")
    def test_post_without_notify_no_email(self, mock_send):
        self.client.post(reverse("add_employee"), self.form_data())
        mock_send.assert_not_called()

    def test_get_renders_modal(self):
        resp = self.client.get(reverse("add_employee"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["show_add_employee_modal"])
        self.assertIn("employee_form", resp.context)

    def test_invalid_form_rerenders_modal(self):
        resp = self.client.post(reverse("add_employee"), self.form_data(email="bad"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["show_add_employee_modal"])
        self.assertTrue(resp.context["employee_form"].errors)


@override_settings(CACHES=_LOCMEM_CACHES)
class SendWelcomeViewTests(TestCase):
    def setUp(self):
        self.admin = make_superuser()
        self.client.force_login(self.admin)
        self.emp = make_employee()

    @patch("schedule.notifications.send_email")
    def test_success(self, mock_send):
        resp = self.client.post(reverse("send_welcome", args=[self.emp.pk]))
        self.assertEqual(resp.status_code, 302)
        mock_send.assert_called_once()

    @patch("schedule.notifications.send_email")
    def test_cooldown_blocks(self, mock_send):
        self.client.post(reverse("send_welcome", args=[self.emp.pk]))
        mock_send.reset_mock()
        self.client.post(reverse("send_welcome", args=[self.emp.pk]))
        mock_send.assert_not_called()


@override_settings(CACHES=_LOCMEM_CACHES)
class SetOverrideEdgeTests(TestCase):
    def setUp(self):
        self.admin = make_superuser()
        self.client.force_login(self.admin)
        self.emp = make_employee()
        self.d = date(2026, 6, 1)

    def test_bad_date_returns_404(self):
        resp = self.client.post(
            reverse("set_override", args=[self.emp.pk, "not-a-date"]),
            {"action": "save", "start_time": "10:00", "end_time": "18:00"},
        )
        self.assertEqual(resp.status_code, 404)

    def test_invalid_time_rejected(self):
        self.client.post(
            reverse("set_override", args=[self.emp.pk, self.d.isoformat()]),
            {"action": "save", "start_time": "garbage", "end_time": "18:00"},
        )
        self.assertFalse(
            ShiftOverride.objects.filter(employee=self.emp, date=self.d).exists()
        )

    def test_partial_time_rejected(self):
        self.client.post(
            reverse("set_override", args=[self.emp.pk, self.d.isoformat()]),
            {"action": "save", "start_time": "10:00", "end_time": ""},
        )
        self.assertFalse(
            ShiftOverride.objects.filter(employee=self.emp, date=self.d).exists()
        )

    def test_end_before_start_rejected(self):
        self.client.post(
            reverse("set_override", args=[self.emp.pk, self.d.isoformat()]),
            {"action": "save", "start_time": "17:00", "end_time": "09:00"},
        )
        self.assertFalse(
            ShiftOverride.objects.filter(employee=self.emp, date=self.d).exists()
        )


@override_settings(CACHES=_LOCMEM_CACHES)
class EmployeeDefaultsEdgeTests(TestCase):
    def setUp(self):
        self.admin = make_superuser()
        self.client.force_login(self.admin)
        self.role = make_role()
        self.emp = make_employee(role=self.role)

    def post(self, data):
        return self.client.post(reverse("employee_defaults", args=[self.emp.pk]), data)

    def test_unknown_form_type_redirects(self):
        resp = self.post({"form": "unknown"})
        self.assertEqual(resp.status_code, 302)

    def test_cycle_weeks_clamped(self):
        self.post({"form": "defaults", "cycle_weeks": "99"})
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.cycle_weeks, 4)

    def test_bad_cycle_string_keeps_current(self):
        self.emp.cycle_weeks = 2
        self.emp.save()
        self.post({"form": "defaults", "cycle_weeks": "notanumber"})
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.cycle_weeks, 2)

    def test_invalid_time_shows_error_and_redirects(self):
        resp = self.post(
            {
                "form": "defaults",
                "cycle_weeks": "1",
                "week_0_day_0_start": "garbage",
                "week_0_day_0_end": "17:00",
            }
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(
            Shift.objects.filter(employee=self.emp, week_offset=0, day=0).exists()
        )

    def test_notify_without_changes_no_send(self):
        Shift.objects.create(
            employee=self.emp,
            week_offset=0,
            day=0,
            start_time="09:00",
            end_time="17:00",
        )
        with patch("schedule.notifications.send_email") as mock_send:
            self.post(
                {
                    "form": "defaults",
                    "cycle_weeks": "1",
                    "week_0_day_0_start": "09:00",
                    "week_0_day_0_end": "17:00",
                    "notify": "1",
                }
            )
            mock_send.assert_not_called()


@override_settings(CACHES=_LOCMEM_CACHES)
class SettingsEdgeTests(TestCase):
    def setUp(self):
        self.admin = make_superuser()
        self.client.force_login(self.admin)
        self.emp = make_employee()

    def test_deactivate_invalid_date_redirects(self):
        resp = self.client.post(
            reverse("settings_deactivate_employee", args=[self.emp.pk]),
            {"last_day": "not-a-date"},
        )
        self.assertEqual(resp.status_code, 302)
        self.emp.refresh_from_db()
        self.assertTrue(self.emp.is_active)

    @patch("schedule.notifications.send_email")
    def test_deactivate_with_notify(self, mock_send):
        user = make_staff_user("deactnotify")
        self.emp.user = user
        self.emp.save()
        future = (timezone.localdate() + timedelta(days=14)).isoformat()
        self.client.post(
            reverse("settings_deactivate_employee", args=[self.emp.pk]),
            {"last_day": future, "notify": "1"},
        )
        mock_send.assert_called_once()

    def test_reactivate_invalid_date_redirects(self):
        self.client.post(
            reverse("settings_deactivate_employee", args=[self.emp.pk]),
            {"last_day": "2026-06-30"},
        )
        resp = self.client.post(
            reverse("settings_reactivate_employee", args=[self.emp.pk]),
            {"reactivation_date": "garbage"},
        )
        self.assertEqual(resp.status_code, 302)

    @patch("schedule.notifications.send_email")
    def test_reactivate_with_notify(self, mock_send):
        self.client.post(
            reverse("settings_deactivate_employee", args=[self.emp.pk]),
            {"last_day": "2026-06-30"},
        )
        mock_send.reset_mock()
        self.client.post(
            reverse("settings_reactivate_employee", args=[self.emp.pk]),
            {"reactivation_date": "2026-09-01", "notify": "1"},
        )
        mock_send.assert_called_once()

    def test_add_title_empty_no_op(self):
        count = Title.objects.count()
        self.client.post(reverse("settings_add_title"), {"name": "   "})
        self.assertEqual(Title.objects.count(), count)

    def test_add_role_empty_no_op(self):
        count = Role.objects.count()
        self.client.post(reverse("settings_add_role"), {"name": ""})
        self.assertEqual(Role.objects.count(), count)

    def test_move_role_out_of_bounds_no_op(self):
        only = self.emp.role
        resp = self.client.post(reverse("settings_move_role", args=[only.pk, "up"]))
        self.assertEqual(resp.status_code, 302)


@override_settings(CACHES=_LOCMEM_CACHES)
class ManagementRequiredTests(TestCase):
    def test_management_group_grants_access(self):
        user = make_staff_user("groupmgr")
        mgmt = Group.objects.create(name="Management")
        user.groups.add(mgmt)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("settings_home")).status_code, 200)
