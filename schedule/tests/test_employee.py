from datetime import date, timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from schedule.models import ShiftPattern

from .factories import make_employee, make_manager_user, make_role, make_staff_user

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


@override_settings(CACHES=_LOCMEM_CACHES)
class EmployeePageGetTests(TestCase):
    def setUp(self):
        self.user = make_manager_user()
        from django.contrib.auth.models import Group, Permission

        mgmt = Group.objects.create(name="Management")
        mgmt.permissions.set(Permission.objects.all())
        self.user.groups.add(mgmt)
        self.client.force_login(self.user)
        self.role = make_role(name="Receptionist", order=20)
        self.emp = make_employee(role=self.role)

    def test_staff_without_view_employee_gets_403(self):
        self.client.logout()
        self.client.force_login(make_staff_user("staff2"))
        resp = self.client.get(reverse("employee_defaults", args=[self.emp.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_inactive_employee_returns_404(self):
        self.emp.is_active = False
        self.emp.last_day = timezone.localdate() - timedelta(days=1)
        self.emp.save()
        resp = self.client.get(reverse("employee_defaults", args=[self.emp.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_get_renders_reading_page(self):
        resp = self.client.get(reverse("employee_defaults", args=[self.emp.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("current_pattern", resp.context)
        self.assertIn("patterns", resp.context)

    def test_pattern_history_displays_mon_sun_range(self):
        # Session 8.5: collapsed history row shows Mon-Sun, not Mon-Mon.
        # Use a far-future date so the current-week card doesn't render
        # the same range (which would double the occurrence count) and
        # so "this week" (the test's actual now) never collides with
        # the assertion dates, whatever day the test runs.
        self.emp.patterns.all().delete()
        ShiftPattern.objects.create(
            employee=self.emp,
            effective_from=date(2099, 1, 5),
            effective_to=date(2099, 1, 12),
            cycle_weeks=1,
        )
        resp = self.client.get(reverse("employee_defaults", args=[self.emp.pk]))
        html = resp.content.decode()
        # Monday start appears once (history row only).
        self.assertEqual(html.count("January 5, 2099"), 1)
        # Sunday end appears once (history row only).
        self.assertEqual(html.count("January 11, 2099"), 1)
        # No "Jan 5 through Jan 5" self-referential range.
        self.assertNotIn("January 5, 2099 through January 5, 2099", html)

    def test_current_pattern_card_displays_sun_end(self):
        # Same range semantics for the "Currently scheduled" card.
        import datetime as _dt

        today = timezone.localdate()
        this_mon = today - _dt.timedelta(days=today.weekday())
        self.emp.patterns.all().delete()
        ShiftPattern.objects.create(
            employee=self.emp,
            effective_from=this_mon,
            effective_to=this_mon + _dt.timedelta(days=7),
            cycle_weeks=1,
        )
        resp = self.client.get(reverse("employee_defaults", args=[self.emp.pk]))
        sunday = this_mon + _dt.timedelta(days=6)
        self.assertContains(resp, sunday.strftime("%B %-d, %Y"))
        # No "Week of <Sunday>" phrasing.
        self.assertNotContains(resp, f"Week of {sunday.strftime('%B %-d, %Y')}")

    def test_set_last_day_button_visible_for_active_employee(self):
        resp = self.client.get(reverse("employee_defaults", args=[self.emp.pk]))
        self.assertContains(resp, 'onclick="openDeactivateModal(this)"')
        self.assertContains(resp, 'id="deactivate-modal"')

    def test_cancel_deactivation_button_visible_when_scheduled(self):
        self.emp.last_day = timezone.localdate() + timedelta(days=14)
        self.emp.is_active = False
        self.emp.save(update_fields=["last_day", "is_active"])
        resp = self.client.get(reverse("employee_defaults", args=[self.emp.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'onclick="openCancelDeactivationModal(this)"')
        self.assertNotContains(resp, 'onclick="openDeactivateModal(this)"')
        self.assertContains(resp, 'id="cancel-deactivation-confirm-modal"')

    def test_send_welcome_email_button_visible_for_active_employee(self):
        resp = self.client.get(reverse("employee_defaults", args=[self.emp.pk]))
        self.assertContains(
            resp,
            f'action="{reverse("send_welcome", args=[self.emp.pk])}"',
        )
        self.assertContains(resp, "Send welcome email")

    def test_send_welcome_email_button_hidden_when_scheduled_for_deactivation(
        self,
    ):
        self.emp.last_day = timezone.localdate() + timedelta(days=14)
        self.emp.is_active = False
        self.emp.save(update_fields=["last_day", "is_active"])
        resp = self.client.get(reverse("employee_defaults", args=[self.emp.pk]))
        self.assertNotContains(resp, "Send welcome email")

    def test_send_welcome_modal_present_for_active_employee(self):
        resp = self.client.get(reverse("employee_defaults", args=[self.emp.pk]))
        self.assertContains(resp, 'id="confirm-send-welcome-modal"')
        self.assertContains(resp, 'id="send-welcome-form"')
        self.assertContains(resp, 'data-employee-email="' + self.emp.email + '"')

    def test_send_welcome_modal_absent_when_scheduled_for_deactivation(self):
        self.emp.last_day = timezone.localdate() + timedelta(days=14)
        self.emp.is_active = False
        self.emp.save(update_fields=["last_day", "is_active"])
        resp = self.client.get(reverse("employee_defaults", args=[self.emp.pk]))
        # No form → no modal is fine either way, but the form itself
        # must be absent (Send welcome email hidden in this state).
        self.assertNotContains(resp, 'id="send-welcome-form"')
