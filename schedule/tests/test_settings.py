from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from schedule.models import Employee, EmploymentPeriod, Role, Title

from .factories import make_employee, make_manager_user, make_role, make_staff_user

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


def make_manager():
    user = make_manager_user(username="mgr")
    mgmt, _ = Group.objects.get_or_create(name="Management")
    mgmt.permissions.set(Permission.objects.all())
    user.groups.add(mgmt)
    return user


@override_settings(CACHES=_LOCMEM_CACHES)
class SettingsPermissionTests(TestCase):
    def test_staff_gets_403(self):
        self.client.force_login(make_staff_user())
        self.assertEqual(self.client.get(reverse("settings_home")).status_code, 403)

    def test_manager_can_view(self):
        self.client.force_login(make_manager())
        self.assertEqual(self.client.get(reverse("settings_home")).status_code, 200)


@override_settings(CACHES=_LOCMEM_CACHES)
class SettingsListTests(TestCase):
    def setUp(self):
        self.client.force_login(make_manager())

    def test_active_includes_future_last_day(self):
        emp = make_employee(email="scheduled@x.com")
        emp.last_day = timezone.localdate() + timedelta(days=10)
        emp.save()
        resp = self.client.get(reverse("settings_home"))
        self.assertIn(emp, resp.context["employees"])

    def test_former_excludes_current(self):
        make_employee(email="active@x.com")
        resp = self.client.get(reverse("settings_home"))
        self.assertEqual(len(resp.context["former_employees"]), 0)

    def test_former_includes_past_last_day(self):
        emp = make_employee(email="former@x.com")
        emp.last_day = timezone.localdate() - timedelta(days=1)
        emp.save()
        resp = self.client.get(reverse("settings_home"))
        self.assertIn(emp, resp.context["former_employees"])


@override_settings(CACHES=_LOCMEM_CACHES)
class DeactivationViewTests(TestCase):
    def setUp(self):
        self.client.force_login(make_manager())
        self.emp = make_employee()

    def test_immediate_deactivation_flips_user(self):
        user = make_staff_user("victim")
        self.emp.user = user
        self.emp.save()
        past = timezone.localdate() - timedelta(days=1)
        self.client.post(
            reverse("settings_deactivate_employee", args=[self.emp.pk]),
            {"last_day": past.isoformat()},
        )
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_future_deactivation_keeps_user_active(self):
        user = make_staff_user("soonleaving")
        self.emp.user = user
        self.emp.save()
        future = timezone.localdate() + timedelta(days=30)
        self.client.post(
            reverse("settings_deactivate_employee", args=[self.emp.pk]),
            {"last_day": future.isoformat()},
        )
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_deactivation_closes_period(self):
        last = date(2026, 6, 30)
        self.client.post(
            reverse("settings_deactivate_employee", args=[self.emp.pk]),
            {"last_day": last.isoformat()},
        )
        self.assertEqual(self.emp.periods.first().end_date, date(2026, 7, 1))

    def test_cancel_reopens_period(self):
        self.client.post(
            reverse("settings_deactivate_employee", args=[self.emp.pk]),
            {"last_day": "2026-06-30"},
        )
        self.client.post(
            reverse("settings_cancel_deactivation", args=[self.emp.pk]),
        )
        self.emp.refresh_from_db()
        self.assertIsNone(self.emp.last_day)
        self.assertTrue(self.emp.is_active)
        self.assertIsNone(self.emp.periods.first().end_date)

    def test_cancel_reactivates_user(self):
        user = make_staff_user("cancelme")
        self.emp.user = user
        self.emp.save()
        past = timezone.localdate() - timedelta(days=1)
        self.client.post(
            reverse("settings_deactivate_employee", args=[self.emp.pk]),
            {"last_day": past.isoformat()},
        )
        self.client.post(
            reverse("settings_cancel_deactivation", args=[self.emp.pk]),
        )
        user.refresh_from_db()
        self.assertTrue(user.is_active)


@override_settings(CACHES=_LOCMEM_CACHES)
class ReactivationViewTests(TestCase):
    def setUp(self):
        self.client.force_login(make_manager())
        self.emp = make_employee(start_date=date(2024, 1, 1))

    def test_creates_new_period(self):
        self.client.post(
            reverse("settings_deactivate_employee", args=[self.emp.pk]),
            {"last_day": "2026-06-30"},
        )
        new_start = date(2026, 9, 1)
        resp = self.client.post(
            reverse("settings_reactivate_employee", args=[self.emp.pk]),
            {"reactivation_date": new_start.isoformat()},
        )
        self.assertEqual(resp.status_code, 302)
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.periods.count(), 2)
        new_period = self.emp.periods.order_by("-start_date").first()
        self.assertEqual(new_period.start_date, new_start)
        self.assertIsNone(new_period.end_date)

    def test_clears_last_day_and_reactivates(self):
        self.client.post(
            reverse("settings_deactivate_employee", args=[self.emp.pk]),
            {"last_day": "2026-06-30"},
        )
        self.client.post(
            reverse("settings_reactivate_employee", args=[self.emp.pk]),
            {"reactivation_date": "2026-09-01"},
        )
        self.emp.refresh_from_db()
        self.assertIsNone(self.emp.last_day)
        self.assertTrue(self.emp.is_active)

    @patch("schedule.notifications.send_welcome_email")
    def test_notify_sends_welcome(self, mock_send):
        mock_send.return_value = (True, None)
        self.client.post(
            reverse("settings_reactivate_employee", args=[self.emp.pk]),
            {"reactivation_date": "2026-09-01", "notify": "1"},
        )
        mock_send.assert_called_once()


@override_settings(CACHES=_LOCMEM_CACHES)
class RoleManagementTests(TestCase):
    def setUp(self):
        self.client.force_login(make_manager())

    def test_add_role(self):
        self.client.post(reverse("settings_add_role"), {"name": "New Role"})
        self.assertTrue(Role.objects.filter(name="New Role").exists())

    def test_move_role_up(self):
        Role.objects.create(name="A", display_order=10)
        b = Role.objects.create(name="B", display_order=20)
        self.client.post(reverse("settings_move_role", args=[b.pk, "up"]))
        roles = list(Role.objects.values_list("name", flat=True))
        self.assertEqual(roles, ["B", "A"])

    def test_move_role_down(self):
        a = Role.objects.create(name="A", display_order=10)
        Role.objects.create(name="B", display_order=20)
        self.client.post(reverse("settings_move_role", args=[a.pk, "down"]))
        roles = list(Role.objects.values_list("name", flat=True))
        self.assertEqual(roles, ["B", "A"])

    def test_move_first_up_is_noop(self):
        a = Role.objects.create(name="A", display_order=10)
        Role.objects.create(name="B", display_order=20)
        self.client.post(reverse("settings_move_role", args=[a.pk, "up"]))
        self.assertEqual(list(Role.objects.values_list("name", flat=True)), ["A", "B"])

    def test_delete_role_in_use_blocked(self):
        role = make_role("In Use")
        make_employee(email="emp@x.com", role=role)
        self.client.post(reverse("settings_delete_role", args=[role.pk]))
        self.assertTrue(Role.objects.filter(pk=role.pk).exists())

    def test_delete_empty_role(self):
        role = Role.objects.create(name="Unused", display_order=99)
        self.client.post(reverse("settings_delete_role", args=[role.pk]))
        self.assertFalse(Role.objects.filter(pk=role.pk).exists())


@override_settings(CACHES=_LOCMEM_CACHES)
class TitleManagementTests(TestCase):
    def setUp(self):
        self.client.force_login(make_manager())

    def test_add_title(self):
        self.client.post(reverse("settings_add_title"), {"name": "Dr."})
        self.assertTrue(Title.objects.filter(name="Dr.").exists())

    def test_delete_title(self):
        title = Title.objects.create(name="ToDelete")
        self.client.post(reverse("settings_delete_title", args=[title.pk]))
        self.assertFalse(Title.objects.filter(pk=title.pk).exists())
