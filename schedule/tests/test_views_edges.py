from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from schedule.models import Employee, Role, Shift, ShiftOverride, ShiftPattern, Title

from .factories import (
    make_employee,
    make_management_user,
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
        self.role = make_role()
        self.emp = make_employee(role=self.role)

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

    @patch("schedule.notifications.send_email")
    def test_next_employee_defaults_redirects_there(self, mock_send):
        resp = self.client.post(
            reverse("send_welcome", args=[self.emp.pk]),
            {"next": "employee_defaults"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("employee_defaults", args=[self.emp.pk]))

    @patch("schedule.notifications.send_email")
    def test_missing_next_defaults_to_settings_home(self, mock_send):
        resp = self.client.post(reverse("send_welcome", args=[self.emp.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("settings_home"))


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
    def test_management_group_plus_perm_grants_access(self):
        """SEC-006: Management AND the required permission grants access."""
        user = make_management_user("groupmgr")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("settings_home")).status_code, 200)

    def test_management_group_without_perm_gets_403(self):
        """SEC-006: Management alone is not enough — the perm is also required.

        A user in the Management group who lacks `view_employee` still
        403s on settings_home. This is the whole point of the AND gate.
        """
        user = make_staff_user("mgmtnoperm")  # view_shift only
        mgmt = Group.objects.create(name="Management")
        user.groups.add(mgmt)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("settings_home")).status_code, 403)


@override_settings(CACHES=_LOCMEM_CACHES)
class Sec006AccessMatrixTests(TestCase):
    """SEC-006: writes require Management AND the view's permission.

    For each view: anonymous → login redirect; permission-only user
    (has perms, not Management) → 403; Management + perm → not 403
    (may be 200, 302, 405, etc. — this test only cares that the
    management gate didn't fire).

    Complements the individual behaviour tests in the view-specific
    test files. Those exercise the success path; this class pins the
    access policy itself so the decorator wiring can't drift.
    """

    def setUp(self):
        self.role = make_role()
        self.emp = make_employee(role=self.role, with_pattern=True)
        self.pattern = self.emp.patterns.first()
        self.perm_user = make_manager_user("perm-only")
        self.mgmt_user = make_management_user("mgmt-perm")
        self.d = date(2026, 6, 1)  # Monday

    def _check(self, url, method="get", data=None):
        data = data or {}

        # Anonymous → login redirect
        self.client.logout()
        resp = getattr(self.client, method)(url, data)
        self.assertEqual(resp.status_code, 302, f"{url} anon expected 302")
        self.assertIn(
            "/accounts/login/",
            resp.url,
            f"{url} anon should redirect to login",
        )

        # Perm-only (has perms, not Management) → 403
        self.client.force_login(self.perm_user)
        resp = getattr(self.client, method)(url, data)
        self.assertEqual(resp.status_code, 403, f"{url} perm-only expected 403")

        # Management + perm → not 403
        self.client.force_login(self.mgmt_user)
        resp = getattr(self.client, method)(url, data)
        self.assertNotEqual(resp.status_code, 403, f"{url} mgmt+perm should not 403")

    # ----- write views -----

    def test_add_employee(self):
        self._check(
            reverse("add_employee"),
            "post",
            data={
                "first_name": "X",
                "last_name": "Y",
                "role": str(self.role.pk),
                "email": "x@x.com",
                "start_date": "2026-01-01",
            },
        )

    def test_schedule_change(self):
        self._check(reverse("schedule_change", args=[self.emp.pk]))

    def test_schedule_add(self):
        self._check(reverse("schedule_add", args=[self.emp.pk]))

    def test_pattern_edit(self):
        self._check(reverse("pattern_edit", args=[self.emp.pk, self.pattern.pk]))

    def test_pattern_form_preview(self):
        self._check(reverse("pattern_form_preview", args=[self.emp.pk]))

    def test_delete_pattern(self):
        later = ShiftPattern.objects.create(
            employee=self.emp,
            effective_from=self.pattern.effective_from + timedelta(weeks=4),
            cycle_weeks=1,
        )
        self._check(reverse("delete_pattern", args=[later.pk]), "post")

    def test_send_welcome(self):
        self._check(reverse("send_welcome", args=[self.emp.pk]), "post")

    def test_set_override(self):
        self._check(
            reverse("set_override", args=[self.emp.pk, self.d.isoformat()]),
            "post",
            data={"action": "off"},
        )

    def test_set_day_override(self):
        self._check(
            reverse("set_day_override", args=[self.d.isoformat()]),
            "post",
            data={"action": "closed"},
        )

    # ----- settings views -----

    def test_settings_home(self):
        self._check(reverse("settings_home"))

    def test_settings_deactivate(self):
        self._check(
            reverse("settings_deactivate_employee", args=[self.emp.pk]),
            "post",
            data={"last_day": "2026-12-31"},
        )

    def test_settings_cancel_deactivation(self):
        self._check(
            reverse("settings_cancel_deactivation", args=[self.emp.pk]),
            "post",
        )

    def test_settings_reactivate(self):
        self._check(
            reverse("settings_reactivate_employee", args=[self.emp.pk]),
            "post",
            data={"reactivation_date": "2026-09-01"},
        )

    def test_settings_add_title(self):
        self._check(reverse("settings_add_title"), "post", data={"name": "Mr."})

    def test_settings_delete_title(self):
        t = Title.objects.create(name="Temp")
        self._check(reverse("settings_delete_title", args=[t.pk]), "post")

    def test_settings_add_role(self):
        self._check(reverse("settings_add_role"), "post", data={"name": "Temp"})

    def test_settings_delete_role(self):
        r = Role.objects.create(name="Unused", display_order=99)
        self._check(reverse("settings_delete_role", args=[r.pk]), "post")

    def test_settings_move_role(self):
        self._check(
            reverse("settings_move_role", args=[self.role.pk, "up"]),
            "post",
        )

    # ----- management-only reads -----

    def test_print_schedule(self):
        self._check(reverse("print_schedule"))

    def test_employee_defaults(self):
        self._check(reverse("employee_defaults", args=[self.emp.pk]))

    def test_employee_details(self):
        self._check(reverse("employee_details", args=[self.emp.pk]))
