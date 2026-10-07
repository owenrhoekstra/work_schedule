from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from schedule.models import DayOverride, Shift, ShiftOverride

from .factories import make_employee, make_manager_user, make_role, make_staff_user

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


def make_manager():
    user = make_manager_user("mgr2")
    mgmt, _ = Group.objects.get_or_create(name="Management")
    mgmt.permissions.set(Permission.objects.all())
    user.groups.add(mgmt)
    return user


@override_settings(CACHES=_LOCMEM_CACHES)
class SetOverrideTests(TestCase):
    def setUp(self):
        self.client.force_login(make_manager())
        self.emp = make_employee()

    def test_save_creates_override(self):
        d = date(2026, 6, 1)
        resp = self.client.post(
            reverse("set_override", args=[self.emp.pk, d.isoformat()]),
            {"action": "save", "start_time": "10:00", "end_time": "18:00"},
        )
        self.assertEqual(resp.status_code, 302)
        ovr = ShiftOverride.objects.get(employee=self.emp, date=d)
        self.assertEqual(ovr.start_time.strftime("%H:%M"), "10:00")
        self.assertEqual(ovr.end_time.strftime("%H:%M"), "18:00")

    def test_off_creates_is_off_override(self):
        d = date(2026, 6, 1)
        self.client.post(
            reverse("set_override", args=[self.emp.pk, d.isoformat()]),
            {"action": "off"},
        )
        self.assertTrue(ShiftOverride.objects.get(employee=self.emp, date=d).is_off)

    def test_reset_deletes_override(self):
        d = date(2026, 6, 1)
        ShiftOverride.objects.create(employee=self.emp, date=d, is_off=True)
        self.client.post(
            reverse("set_override", args=[self.emp.pk, d.isoformat()]),
            {"action": "reset"},
        )
        self.assertFalse(
            ShiftOverride.objects.filter(employee=self.emp, date=d).exists()
        )

    def test_end_before_start_rejected(self):
        d = date(2026, 6, 1)
        self.client.post(
            reverse("set_override", args=[self.emp.pk, d.isoformat()]),
            {"action": "save", "start_time": "17:00", "end_time": "09:00"},
        )
        self.assertFalse(
            ShiftOverride.objects.filter(employee=self.emp, date=d).exists()
        )

    def test_staff_without_permission_gets_403(self):
        self.client.logout()
        self.client.force_login(make_staff_user("noperm"))
        d = date(2026, 6, 1)
        resp = self.client.post(
            reverse("set_override", args=[self.emp.pk, d.isoformat()]),
            {"action": "save", "start_time": "10:00", "end_time": "18:00"},
        )
        self.assertEqual(resp.status_code, 403)

    @patch("schedule.notifications.send_email")
    def test_notify_sends_when_changed(self, mock_send):
        # Notifications require a linked, active user
        user = make_staff_user("overrideuser")
        self.emp.user = user
        self.emp.email = user.email
        self.emp.save()
        pattern = self.emp.patterns.first()
        Shift.objects.create(
            pattern=pattern,
            week_offset=0,
            day=date(2026, 6, 1).weekday(),
            start_time="09:00",
            end_time="17:00",
        )
        d = date(2026, 6, 1)
        self.client.post(
            reverse("set_override", args=[self.emp.pk, d.isoformat()]),
            {
                "action": "save",
                "start_time": "10:00",
                "end_time": "18:00",
                "notify": "1",
            },
        )
        mock_send.assert_called_once()

    @patch("schedule.notifications.send_email")
    def test_no_notify_when_unchanged(self, mock_send):
        d = date(2026, 6, 1)
        ShiftOverride.objects.create(
            employee=self.emp,
            date=d,
            start_time="10:00",
            end_time="18:00",
        )
        self.client.post(
            reverse("set_override", args=[self.emp.pk, d.isoformat()]),
            {
                "action": "save",
                "start_time": "10:00",
                "end_time": "18:00",
                "notify": "1",
            },
        )
        mock_send.assert_not_called()


@override_settings(CACHES=_LOCMEM_CACHES)
class SetDayOverrideTests(TestCase):
    def setUp(self):
        self.client.force_login(make_manager())

    def test_closed(self):
        d = date(2026, 6, 1)
        self.client.post(
            reverse("set_day_override", args=[d.isoformat()]),
            {"action": "closed"},
        )
        self.assertTrue(DayOverride.objects.filter(date=d, status="closed").exists())

    def test_holiday(self):
        d = date(2026, 6, 1)
        self.client.post(
            reverse("set_day_override", args=[d.isoformat()]),
            {"action": "holiday"},
        )
        self.assertTrue(DayOverride.objects.filter(date=d, status="holiday").exists())

    def test_clear(self):
        d = date(2026, 6, 1)
        DayOverride.objects.create(date=d, status="closed")
        self.client.post(
            reverse("set_day_override", args=[d.isoformat()]),
            {"action": "clear"},
        )
        self.assertFalse(DayOverride.objects.filter(date=d).exists())

    def test_change_status_overwrites(self):
        d = date(2026, 6, 1)
        DayOverride.objects.create(date=d, status="closed")
        self.client.post(
            reverse("set_day_override", args=[d.isoformat()]),
            {"action": "holiday"},
        )
        self.assertEqual(DayOverride.objects.get(date=d).status, "holiday")

    def test_staff_without_change_shift_gets_403(self):
        self.client.logout()
        self.client.force_login(make_staff_user("staffd"))
        d = date(2026, 6, 1)
        resp = self.client.post(
            reverse("set_day_override", args=[d.isoformat()]),
            {"action": "closed"},
        )
        self.assertEqual(resp.status_code, 403)
