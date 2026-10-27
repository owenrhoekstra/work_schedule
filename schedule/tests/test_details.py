"""Coverage for the employee details page (/details/).

Session 7. Identity editing and deactivation move off the reading
page; the reading page becomes read-only. All details-page access is
gated on Management (superuser or Management group).

Session 7.5 adds scheduled-deactivation UX: when last_day is set, a
banner appears and the footer swaps the Set Last Day trigger for a
Cancel deactivation trigger. Tests for those variants assert on the
trigger buttons' distinctive `onclick` attributes — the modals
themselves are always rendered, and their button text overlaps the
trigger button text, so text-matching produces false positives.

Session 8.5: `date.today()` replaced with `timezone.localdate()`
throughout to prevent midnight flake (per AGENTS.md — timezone
differences between server and TIME_ZONE can flip tests at midnight).
"""

from datetime import date, timedelta

from django.contrib.auth.models import Group, Permission
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from schedule.models import ShiftPattern

from .factories import make_employee, make_manager_user, make_role, make_staff_user

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


def _manager(client):
    """Log in a superuser-like manager with Management group membership."""
    user = make_manager_user()
    mgmt = Group.objects.get_or_create(name="Management")[0]
    mgmt.permissions.set(Permission.objects.all())
    user.groups.add(mgmt)
    client.force_login(user)
    return user


@override_settings(CACHES=_LOCMEM_CACHES)
class EmployeeDetailsGetTests(TestCase):
    def setUp(self):
        _manager(self.client)
        self.role = make_role(name="Receptionist", order=20)
        self.emp = make_employee(role=self.role)

    def test_staff_without_management_gets_403(self):
        self.client.logout()
        self.client.force_login(make_staff_user("nonmanager"))
        resp = self.client.get(reverse("employee_details", args=[self.emp.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_inactive_employee_returns_404(self):
        self.emp.is_active = False
        self.emp.last_day = timezone.localdate() - timedelta(days=1)
        self.emp.save()
        resp = self.client.get(reverse("employee_details", args=[self.emp.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_get_renders_edit_page(self):
        resp = self.client.get(reverse("employee_details", args=[self.emp.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("identity_form", resp.context)
        self.assertIn("today", resp.context)
        self.assertContains(resp, 'id="deactivate-modal"')
        self.assertContains(resp, 'id="confirm-discard-modal"')


@override_settings(CACHES=_LOCMEM_CACHES)
class EmployeeDetailsPostTests(TestCase):
    def setUp(self):
        _manager(self.client)
        self.role = make_role(name="Receptionist", order=20)
        self.emp = make_employee(role=self.role, with_pattern=True)

    def post_identity(self, **overrides):
        data = {
            "form": "identity",
            "title": "",
            "first_name": "Updated",
            "last_name": "Name",
            "role": str(self.role.pk),
            "email": self.emp.email,
            "start_date": self.emp.start_date.isoformat(),
        }
        data.update(overrides)
        return self.client.post(reverse("employee_details", args=[self.emp.pk]), data)

    def test_basic_update_redirects_to_reading_page(self):
        resp = self.post_identity(first_name="New")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("employee_defaults", args=[self.emp.pk]))
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.first_name, "New")

    def test_start_date_change_syncs_period(self):
        new = date(2026, 1, 15)
        resp = self.post_identity(start_date=new.isoformat())
        self.assertEqual(resp.status_code, 302)
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.start_date, new)
        self.assertEqual(self.emp.periods.first().start_date, new)

    def test_start_after_period_end_rerenders_details_page(self):
        period = self.emp.periods.first()
        period.end_date = date(2026, 6, 1)
        period.save()
        resp = self.post_identity(start_date="2026-07-01")
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "schedule/employee_details.html")
        self.assertTrue(resp.context["identity_form"].errors)

    def test_duplicate_email_rerenders_details_page(self):
        other = make_employee(email="other@x.com")
        resp = self.post_identity(email=other.email)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "schedule/employee_details.html")
        self.assertTrue(resp.context["identity_form"].errors)

    def test_start_date_earlier_slides_earliest_pattern_backward(self):
        pattern = self.emp.patterns.first()
        pattern.effective_from = date(2025, 6, 2)
        pattern.save(update_fields=["effective_from"])

        new_start = date(2024, 11, 7)
        resp = self.post_identity(start_date=new_start.isoformat())
        self.assertEqual(resp.status_code, 302)

        pattern.refresh_from_db()
        self.assertEqual(pattern.effective_from, date(2024, 11, 4))

    def test_start_date_later_slides_earliest_pattern_forward_when_no_collision(
        self,
    ):
        self.emp.patterns.all().delete()
        ShiftPattern.objects.create(
            employee=self.emp, effective_from=date(2025, 1, 6), cycle_weeks=1
        )
        ShiftPattern.objects.create(
            employee=self.emp, effective_from=date(2025, 6, 2), cycle_weeks=1
        )

        resp = self.post_identity(start_date=date(2025, 3, 1).isoformat())
        self.assertEqual(resp.status_code, 302)

        earliest = self.emp.patterns.order_by("effective_from").first()
        self.assertEqual(earliest.effective_from, date(2025, 2, 24))

    def test_start_date_later_does_not_collide_with_next_pattern(self):
        self.emp.patterns.all().delete()
        ShiftPattern.objects.create(
            employee=self.emp, effective_from=date(2025, 1, 6), cycle_weeks=1
        )
        ShiftPattern.objects.create(
            employee=self.emp, effective_from=date(2025, 2, 3), cycle_weeks=1
        )

        resp = self.post_identity(start_date=date(2025, 2, 10).isoformat())
        self.assertEqual(resp.status_code, 302)

        earliest = self.emp.patterns.order_by("effective_from").first()
        self.assertEqual(earliest.effective_from, date(2025, 1, 6))


@override_settings(CACHES=_LOCMEM_CACHES)
class DeactivationRedirectTests(TestCase):
    """settings_deactivate_employee honours the `next` POST field."""

    def setUp(self):
        _manager(self.client)
        self.emp = make_employee()

    def test_next_employee_defaults_redirects_to_reading_page(self):
        resp = self.client.post(
            reverse("settings_deactivate_employee", args=[self.emp.pk]),
            {
                "last_day": (timezone.localdate() + timedelta(days=7)).isoformat(),
                "next": "employee_defaults",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("employee_defaults", args=[self.emp.pk]))

    def test_missing_next_defaults_to_settings_home(self):
        resp = self.client.post(
            reverse("settings_deactivate_employee", args=[self.emp.pk]),
            {"last_day": (timezone.localdate() + timedelta(days=7)).isoformat()},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("settings_home"))

    def test_unknown_next_falls_back_to_settings_home(self):
        resp = self.client.post(
            reverse("settings_deactivate_employee", args=[self.emp.pk]),
            {
                "last_day": (timezone.localdate() + timedelta(days=7)).isoformat(),
                "next": "malicious_target",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("settings_home"))

    def test_immediate_deactivation_overrides_employee_defaults_target(self):
        # Session 9 (CodeRabbit): an immediate deactivation puts the
        # employee below today's last_day cutoff, which 404s the
        # reading page. The redirect must fall back to settings_home
        # even when next=employee_defaults was requested.
        resp = self.client.post(
            reverse("settings_deactivate_employee", args=[self.emp.pk]),
            {
                "last_day": (timezone.localdate() - timedelta(days=1)).isoformat(),
                "next": "employee_defaults",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("settings_home"))

    def test_future_deactivation_honours_employee_defaults_target(self):
        # Non-immediate deactivation: last_day is in the future, so
        # the reading page still includes the employee. Honour next.
        resp = self.client.post(
            reverse("settings_deactivate_employee", args=[self.emp.pk]),
            {
                "last_day": (timezone.localdate() + timedelta(days=30)).isoformat(),
                "next": "employee_defaults",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("employee_defaults", args=[self.emp.pk]))


@override_settings(CACHES=_LOCMEM_CACHES)
class DetailsScheduledDeactivationTests(TestCase):
    """Session 7.5: scheduled-deactivation UX on /details/.

    Asserts on the trigger buttons' distinctive `onclick` attributes
    rather than the visible button text — the modals themselves are
    always rendered, so text-matching produces false positives.
    """

    def setUp(self):
        _manager(self.client)
        self.emp = make_employee()

    def test_no_last_day_shows_set_last_day_trigger(self):
        resp = self.client.get(reverse("employee_details", args=[self.emp.pk]))
        self.assertContains(resp, 'onclick="openDeactivateModal(this)"')
        self.assertNotContains(resp, 'onclick="openCancelDeactivationModal(this)"')
        self.assertNotContains(resp, "Scheduled for deactivation")

    def test_last_day_set_shows_banner_and_cancel_trigger(self):
        self.emp.last_day = timezone.localdate() + timedelta(days=14)
        self.emp.is_active = False
        self.emp.save(update_fields=["last_day", "is_active"])
        resp = self.client.get(reverse("employee_details", args=[self.emp.pk]))
        self.assertContains(resp, "Scheduled for deactivation")
        self.assertContains(resp, 'onclick="openCancelDeactivationModal(this)"')
        self.assertNotContains(resp, 'onclick="openDeactivateModal(this)"')

    def test_cancel_deactivation_modal_present(self):
        resp = self.client.get(reverse("employee_details", args=[self.emp.pk]))
        self.assertContains(resp, 'id="cancel-deactivation-confirm-modal"')

    def test_save_details_modal_present(self):
        resp = self.client.get(reverse("employee_details", args=[self.emp.pk]))
        self.assertContains(resp, 'id="confirm-save-details-modal"')


@override_settings(CACHES=_LOCMEM_CACHES)
class CancelDeactivationNextTests(TestCase):
    """settings_cancel_deactivation honours `next` field (Session 7.5)."""

    def setUp(self):
        _manager(self.client)
        self.emp = make_employee()
        self.emp.last_day = timezone.localdate() + timedelta(days=7)
        self.emp.is_active = False
        self.emp.save(update_fields=["last_day", "is_active"])
        p = self.emp.periods.filter(end_date__isnull=True).first()
        if p:
            p.end_date = self.emp.last_day + timedelta(days=1)
            p.save(update_fields=["end_date"])

    def test_next_employee_details_redirects_there(self):
        resp = self.client.post(
            reverse("settings_cancel_deactivation", args=[self.emp.pk]),
            {"next": "employee_details"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("employee_details", args=[self.emp.pk]))

    def test_next_employee_defaults_redirects_there(self):
        resp = self.client.post(
            reverse("settings_cancel_deactivation", args=[self.emp.pk]),
            {"next": "employee_defaults"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("employee_defaults", args=[self.emp.pk]))

    def test_missing_next_defaults_to_settings_home(self):
        resp = self.client.post(
            reverse("settings_cancel_deactivation", args=[self.emp.pk]),
            {},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("settings_home"))

    def test_cancel_clears_last_day_and_reopens_period(self):
        self.client.post(
            reverse("settings_cancel_deactivation", args=[self.emp.pk]),
            {"next": "employee_details"},
        )
        self.emp.refresh_from_db()
        self.assertIsNone(self.emp.last_day)
        self.assertTrue(self.emp.is_active)
        latest = self.emp.periods.order_by("-start_date").first()
        self.assertIsNone(latest.end_date)
