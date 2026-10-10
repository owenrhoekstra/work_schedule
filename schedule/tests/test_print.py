from datetime import date, timedelta

from django.contrib.auth.models import Group, Permission
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from schedule.views import _ordinal

from .factories import make_employee, make_manager_user, make_role, make_staff_user

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


def _make_manager(username="printmgr"):
    user = make_manager_user(username)
    mgmt, _ = Group.objects.get_or_create(name="Management")
    mgmt.permissions.set(Permission.objects.all())
    user.groups.add(mgmt)
    return user


def _first_monday_of_june(year):
    """The Monday of the first week that overlaps June in `year`.

    Used by the range-label tests so the anchor date is a real Monday
    in June for whatever year the tests happen to run in.
    """
    d = date(year, 6, 1)
    return d + timedelta(days=(7 - d.weekday()) % 7)


@override_settings(CACHES=_LOCMEM_CACHES)
class PrintScheduleTests(TestCase):
    def setUp(self):
        self.client.force_login(_make_manager())
        role = make_role("Receptionist", order=20)
        make_employee(role=role)

    def test_anonymous_redirected_to_login(self):
        self.client.logout()
        resp = self.client.get(reverse("print_schedule"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)

    def test_staff_without_management_gets_403(self):
        self.client.logout()
        self.client.force_login(make_staff_user("printstaff"))
        resp = self.client.get(reverse("print_schedule"))
        self.assertEqual(resp.status_code, 403)

    def test_defaults_to_current_week_and_one_week(self):
        resp = self.client.get(reverse("print_schedule"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context["weeks"]), 1)
        today = timezone.localdate()
        this_monday = today - timedelta(days=today.weekday())
        self.assertEqual(resp.context["anchor"], this_monday)

    def test_weeks_param_respected(self):
        resp = self.client.get(reverse("print_schedule"), {"weeks": "3"})
        self.assertEqual(len(resp.context["weeks"]), 3)

    def test_weeks_param_clamped_high(self):
        resp = self.client.get(reverse("print_schedule"), {"weeks": "99"})
        self.assertEqual(len(resp.context["weeks"]), 4)

    def test_weeks_param_clamped_low(self):
        resp = self.client.get(reverse("print_schedule"), {"weeks": "0"})
        self.assertEqual(len(resp.context["weeks"]), 1)

    def test_weeks_param_invalid_falls_back_to_one(self):
        resp = self.client.get(reverse("print_schedule"), {"weeks": "abc"})
        self.assertEqual(len(resp.context["weeks"]), 1)

    def test_week_param_respected(self):
        resp = self.client.get(reverse("print_schedule"), {"week": "2026-06-03"})
        self.assertEqual(resp.context["anchor"], date(2026, 6, 1))

    def test_week_param_invalid_falls_back_to_current(self):
        resp = self.client.get(reverse("print_schedule"), {"week": "nonsense"})
        today = timezone.localdate()
        this_monday = today - timedelta(days=today.weekday())
        self.assertEqual(resp.context["anchor"], this_monday)

    def test_consecutive_weeks_are_ordered(self):
        resp = self.client.get(
            reverse("print_schedule"), {"week": "2026-06-01", "weeks": "3"}
        )
        anchors = [w["week_start"] for w in resp.context["weeks"]]
        self.assertEqual(
            anchors,
            [date(2026, 6, 1), date(2026, 6, 8), date(2026, 6, 15)],
        )

    def test_color_defaults_to_color_mode(self):
        resp = self.client.get(reverse("print_schedule"))
        self.assertEqual(resp.context["color_mode"], "color")

    def test_color_param_bw(self):
        resp = self.client.get(reverse("print_schedule"), {"color": "bw"})
        self.assertEqual(resp.context["color_mode"], "bw")

    def test_color_param_invalid_falls_back_to_color(self):
        resp = self.client.get(reverse("print_schedule"), {"color": "rainbow"})
        self.assertEqual(resp.context["color_mode"], "color")

    # ----- range label -----
    #
    # The label composes the first week's title with the short form of
    # the last week's title. `_week_title_for` appends a year suffix
    # only when the week's year differs from the current year, so
    # anchoring tests in the current year keeps the expected strings
    # stable across calendar rollovers.

    def test_range_label_single_week(self):
        anchor = _first_monday_of_june(timezone.localdate().year)
        resp = self.client.get(
            reverse("print_schedule"),
            {"week": anchor.isoformat(), "weeks": "1"},
        )
        self.assertEqual(
            resp.context["range_label"],
            f"Week of June {_ordinal(anchor.day)}",
        )

    def test_range_label_multi_week(self):
        anchor = _first_monday_of_june(timezone.localdate().year)
        end = anchor + timedelta(weeks=1)
        resp = self.client.get(
            reverse("print_schedule"),
            {"week": anchor.isoformat(), "weeks": "2"},
        )
        self.assertEqual(
            resp.context["range_label"],
            f"Week of June {_ordinal(anchor.day)} – June {_ordinal(end.day)}",
        )

    def test_paper_has_mode_class(self):
        resp = self.client.get(reverse("print_schedule"), {"color": "bw"})
        self.assertContains(resp, "mode-bw")


@override_settings(CACHES=_LOCMEM_CACHES)
class QRCodeTests(TestCase):
    def setUp(self):
        self.client.force_login(_make_manager())

    def test_requires_auth(self):
        self.client.logout()
        resp = self.client.get(reverse("qr_code"))
        self.assertEqual(resp.status_code, 302)

    def test_returns_svg(self):
        resp = self.client.get(reverse("qr_code"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "image/svg+xml")
        self.assertIn(b"<svg", resp.content[:200])


@override_settings(CACHES=_LOCMEM_CACHES)
class HomePrintButtonTests(TestCase):
    def test_management_sees_print_button(self):
        self.client.force_login(_make_manager("homeprint"))
        resp = self.client.get(reverse("home"))
        self.assertContains(resp, "print-modal")

    def test_non_management_does_not_see_print_button(self):
        self.client.force_login(make_staff_user("noprint"))
        resp = self.client.get(reverse("home"))
        self.assertNotContains(resp, "print-modal")