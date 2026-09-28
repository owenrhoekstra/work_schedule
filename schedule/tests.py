from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth.models import Permission, User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    DayOverride,
    Employee,
    EmploymentPeriod,
    Role,
    Shift,
    ShiftOverride,
    Title,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

_LOCMEM_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}


def make_role(name="Staff", order=10):
    role, _ = Role.objects.get_or_create(name=name, defaults={"display_order": order})
    return role


def make_title(name="Dr."):
    return Title.objects.create(name=name)


def make_employee(email="test@example.com", role=None, start_date=None, **kwargs):
    role = role or make_role()
    return Employee.objects.create(
        first_name=kwargs.pop("first_name", "Test"),
        last_name=kwargs.pop("last_name", "User"),
        email=email,
        role=role,
        start_date=start_date or date.today(),
        **kwargs,
    )


def make_superuser(username="admin"):
    return User.objects.create_superuser(
        username=username, password="pass", email=f"{username}@example.com"
    )


def make_staff_user(username="staff"):
    """A staff-level user: has view_shift but no Management group."""
    user = User.objects.create_user(
        username=username, password="pass", email=f"{username}@example.com"
    )
    user.user_permissions.add(Permission.objects.get(codename="view_shift"))
    return user


# ---------------------------------------------------------------------------
# Signals / model behavior
# ---------------------------------------------------------------------------


@override_settings(CACHES=_LOCMEM_CACHES)
class EmployeeSignalTests(TestCase):
    def test_creating_employee_creates_employment_period(self):
        emp = make_employee(start_date=date(2026, 1, 1))
        self.assertEqual(emp.periods.count(), 1)
        period = emp.periods.first()
        self.assertEqual(period.start_date, date(2026, 1, 1))
        self.assertIsNone(period.end_date)

    def test_employee_with_last_day_on_create_gets_closed_period(self):
        emp = make_employee(
            start_date=date(2026, 1, 1),
            last_day=date(2026, 3, 31),
        )
        period = emp.periods.first()
        self.assertEqual(period.end_date, date(2026, 4, 1))

    def test_updating_employee_name_mirrors_to_user(self):
        user = make_staff_user()
        emp = make_employee(email=user.email)
        emp.user = user
        emp.save()
        emp.first_name = "Changed"
        emp.save()
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Changed")


# ---------------------------------------------------------------------------
# Cycle math
# ---------------------------------------------------------------------------


@override_settings(CACHES=_LOCMEM_CACHES)
class CycleMathTests(TestCase):
    def test_single_week_always_zero(self):
        from django.conf import settings

        from schedule.views import _week_offset_for

        emp = make_employee(cycle_weeks=1)
        self.assertEqual(_week_offset_for(settings.CYCLE_EPOCH, emp), 0)
        self.assertEqual(
            _week_offset_for(settings.CYCLE_EPOCH + timedelta(weeks=52), emp), 0
        )

    def test_two_week_cycle_alternates(self):
        from django.conf import settings

        from schedule.views import _week_offset_for

        emp = make_employee(cycle_weeks=2)
        epoch = settings.CYCLE_EPOCH
        self.assertEqual(_week_offset_for(epoch, emp), 0)
        self.assertEqual(_week_offset_for(epoch + timedelta(weeks=1), emp), 1)
        self.assertEqual(_week_offset_for(epoch + timedelta(weeks=2), emp), 0)
        self.assertEqual(_week_offset_for(epoch + timedelta(weeks=3), emp), 1)


# ---------------------------------------------------------------------------
# Home view
# ---------------------------------------------------------------------------


@override_settings(CACHES=_LOCMEM_CACHES)
class HomeViewTests(TestCase):
    def setUp(self):
        self.user = make_staff_user()
        self.client.force_login(self.user)

    def test_staff_can_view_schedule(self):
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)

    def test_anonymous_redirected_to_login(self):
        self.client.logout()
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)

    def test_user_without_view_shift_gets_403(self):
        other = User.objects.create_user(username="nope", password="p")
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("home")).status_code, 403)

    def test_week_param_accepted(self):
        resp = self.client.get(reverse("home"), {"week": "2026-01-05"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["week_start"], date(2026, 1, 5))

    def test_invalid_week_param_falls_back(self):
        resp = self.client.get(reverse("home"), {"week": "garbage"})
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# Employee defaults page — merged identity + defaults
# ---------------------------------------------------------------------------


@override_settings(CACHES=_LOCMEM_CACHES)
class EmployeeDefaultsViewTests(TestCase):
    def setUp(self):
        self.user = make_superuser()
        self.client.force_login(self.user)
        self.role = make_role(name="Receptionist", order=20)
        self.emp = make_employee(role=self.role)

    def test_get_renders_both_forms(self):
        resp = self.client.get(reverse("employee_defaults", args=[self.emp.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("identity_form", resp.context)
        self.assertIn("weeks", resp.context)

    def test_identity_save_updates_start_date_and_period(self):
        new_start = date(2026, 1, 15)
        resp = self.client.post(
            reverse("employee_defaults", args=[self.emp.pk]),
            {
                "form": "identity",
                "title": "",
                "first_name": "New",
                "last_name": "Name",
                "role": str(self.role.pk),
                "email": self.emp.email,
                "start_date": new_start.isoformat(),
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.start_date, new_start)
        self.assertEqual(self.emp.periods.first().start_date, new_start)

    def test_identity_save_rejects_start_after_period_end(self):
        period = self.emp.periods.first()
        period.end_date = date(2026, 6, 1)
        period.save()
        resp = self.client.post(
            reverse("employee_defaults", args=[self.emp.pk]),
            {
                "form": "identity",
                "title": "",
                "first_name": "New",
                "last_name": "Name",
                "role": str(self.role.pk),
                "email": self.emp.email,
                "start_date": "2026-07-01",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["identity_form"].errors)

    def test_defaults_save_creates_shift(self):
        resp = self.client.post(
            reverse("employee_defaults", args=[self.emp.pk]),
            {
                "form": "defaults",
                "cycle_weeks": "1",
                "week_0_day_0_start": "09:00",
                "week_0_day_0_end": "17:00",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            Shift.objects.filter(employee=self.emp, week_offset=0, day=0).exists()
        )

    def test_defaults_save_rejects_end_before_start(self):
        self.client.post(
            reverse("employee_defaults", args=[self.emp.pk]),
            {
                "form": "defaults",
                "cycle_weeks": "1",
                "week_0_day_0_start": "17:00",
                "week_0_day_0_end": "09:00",
            },
        )
        self.assertFalse(
            Shift.objects.filter(employee=self.emp, week_offset=0, day=0).exists()
        )


# ---------------------------------------------------------------------------
# Deactivation / reactivation
# ---------------------------------------------------------------------------


@override_settings(CACHES=_LOCMEM_CACHES)
class DeactivationTests(TestCase):
    def setUp(self):
        self.user = make_superuser()
        self.client.force_login(self.user)
        self.emp = make_employee()

    def test_deactivate_sets_last_day_and_closes_period(self):
        last = date(2026, 6, 30)
        resp = self.client.post(
            reverse("settings_deactivate_employee", args=[self.emp.pk]),
            {"last_day": last.isoformat()},
        )
        self.assertEqual(resp.status_code, 302)
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.last_day, last)
        self.assertFalse(self.emp.is_active)
        self.assertEqual(self.emp.periods.first().end_date, date(2026, 7, 1))

    def test_future_deactivation_keeps_user_active(self):
        user = make_staff_user()
        emp = make_employee(email=user.email)
        emp.user = user
        emp.save()
        future = timezone.localdate() + timedelta(days=30)
        self.client.post(
            reverse("settings_deactivate_employee", args=[emp.pk]),
            {"last_day": future.isoformat()},
        )
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_past_deactivation_flips_user_off(self):
        user = make_staff_user()
        emp = make_employee(email=user.email)
        emp.user = user
        emp.save()
        past = timezone.localdate() - timedelta(days=1)
        self.client.post(
            reverse("settings_deactivate_employee", args=[emp.pk]),
            {"last_day": past.isoformat()},
        )
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_reactivate_opens_new_period(self):
        # Give the employee a start date well in the past so the
        # deactivation and reactivation dates land in a coherent range.
        self.emp.start_date = date(2024, 1, 1)
        self.emp.save()
        first_period = self.emp.periods.first()
        first_period.start_date = date(2024, 1, 1)
        first_period.save()

        self.client.post(
            reverse("settings_deactivate_employee", args=[self.emp.pk]),
            {"last_day": "2026-06-30"},
        )
        reactivate_at = date(2026, 9, 1)
        resp = self.client.post(
            reverse("settings_reactivate_employee", args=[self.emp.pk]),
            {"reactivation_date": reactivate_at.isoformat()},
        )
        self.assertEqual(resp.status_code, 302)
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.periods.count(), 2)
        new_period = self.emp.periods.order_by("-start_date").first()
        self.assertEqual(new_period.start_date, reactivate_at)
        self.assertIsNone(new_period.end_date)
        self.assertIsNone(self.emp.last_day)

    def test_cancel_deactivation_reopens_period(self):
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


# ---------------------------------------------------------------------------
# Overrides
# ---------------------------------------------------------------------------


@override_settings(CACHES=_LOCMEM_CACHES)
class OverrideTests(TestCase):
    def setUp(self):
        self.user = make_superuser()
        self.client.force_login(self.user)
        self.emp = make_employee()

    def test_set_override_save(self):
        d = date(2026, 6, 1)
        resp = self.client.post(
            reverse("set_override", args=[self.emp.pk, d.isoformat()]),
            {"action": "save", "start_time": "10:00", "end_time": "18:00"},
        )
        self.assertEqual(resp.status_code, 302)
        ovr = ShiftOverride.objects.get(employee=self.emp, date=d)
        self.assertFalse(ovr.is_off)
        self.assertEqual(ovr.start_time.strftime("%H:%M"), "10:00")

    def test_set_override_off(self):
        d = date(2026, 6, 1)
        self.client.post(
            reverse("set_override", args=[self.emp.pk, d.isoformat()]),
            {"action": "off"},
        )
        self.assertTrue(ShiftOverride.objects.get(employee=self.emp, date=d).is_off)

    def test_set_override_reset(self):
        d = date(2026, 6, 1)
        ShiftOverride.objects.create(employee=self.emp, date=d, is_off=True)
        self.client.post(
            reverse("set_override", args=[self.emp.pk, d.isoformat()]),
            {"action": "reset"},
        )
        self.assertFalse(
            ShiftOverride.objects.filter(employee=self.emp, date=d).exists()
        )

    def test_day_override_closed(self):
        d = date(2026, 6, 1)
        self.client.post(
            reverse("set_day_override", args=[d.isoformat()]),
            {"action": "closed"},
        )
        self.assertTrue(DayOverride.objects.filter(date=d, status="closed").exists())

    def test_day_override_clear(self):
        d = date(2026, 6, 1)
        DayOverride.objects.create(date=d, status="closed")
        self.client.post(
            reverse("set_day_override", args=[d.isoformat()]),
            {"action": "clear"},
        )
        self.assertFalse(DayOverride.objects.filter(date=d).exists())


# ---------------------------------------------------------------------------
# Deactivation middleware
# ---------------------------------------------------------------------------


@override_settings(CACHES=_LOCMEM_CACHES)
class DeactivationMiddlewareTests(TestCase):
    def test_user_past_last_day_is_kicked_out(self):
        user = make_staff_user()
        emp = make_employee(email=user.email)
        emp.user = user
        emp.last_day = timezone.localdate() - timedelta(days=1)
        emp.save()
        user.is_active = True
        user.save(update_fields=["is_active"])

        self.client.force_login(user)
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_user_on_last_day_still_allowed(self):
        user = make_staff_user()
        emp = make_employee(email=user.email)
        emp.user = user
        emp.last_day = timezone.localdate()
        emp.save()
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)


# ---------------------------------------------------------------------------
# Permission boundaries
# ---------------------------------------------------------------------------


@override_settings(CACHES=_LOCMEM_CACHES)
class PermissionBoundaryTests(TestCase):
    def setUp(self):
        self.staff = make_staff_user()
        self.emp = make_employee()

    def test_staff_cannot_reach_settings(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("settings_home"))
        self.assertEqual(resp.status_code, 403)

    def test_staff_cannot_edit_defaults(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("employee_defaults", args=[self.emp.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_manager_can_reach_settings(self):
        manager = make_superuser()
        self.client.force_login(manager)
        self.assertEqual(self.client.get(reverse("settings_home")).status_code, 200)
