# schedule/tests/test_day_override_api.py
from datetime import date

from django.contrib.auth.models import Permission, User
from django.test import TestCase

from schedule.models import CompanyMembership, DayOverride, Team

from ._helpers import login_as
from .factories import (
    make_company,
    make_employee,
    make_manager_user,
    make_member_user,
)

DAY = date(2026, 11, 24)
DAY_URL = f"/api/v1/schedule/overrides/days/{DAY.isoformat()}/"


def make_company_admin(
    username,
    company,
    perms=("change_dayoverride", "view_shift"),  # was "change_shift"
):
    """Company admin WITHOUT the Platform Admin group, so is_company_admin
    is decided purely by the membership row. (make_management_user adds
    the group, which bypasses per-company checks.)"""
    user = User.objects.create_user(
        username=username, password="pass", email=f"{username}@example.com"
    )
    user.user_permissions.set(
        Permission.objects.filter(
            content_type__app_label="schedule", codename__in=perms
        )
    )
    CompanyMembership.objects.create(
        user=user, company=company, role="admin", status="active"
    )
    return user


class DayOverrideApiTests(TestCase):
    def setUp(self):
        self.company = make_company("A")

    def post_day(self, action):
        return self.client.post(
            DAY_URL, {"action": action}, content_type="application/json"
        )

    def test_admin_with_perms_can_set_and_clear(self):
        admin = make_company_admin(
            "admin",
            self.company,
            perms=("change_dayoverride", "view_shift"),
        )
        login_as(self.client, admin, company=self.company)

        r = self.post_day("closed")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "closed")
        self.assertTrue(
            DayOverride.objects.filter(date=DAY, company=self.company).exists()
        )

        r = self.post_day("holiday")  # update_or_create path, no duplicate row
        self.assertEqual(r.json()["status"], "holiday")
        self.assertEqual(
            DayOverride.objects.filter(date=DAY, company=self.company).count(), 1
        )

        r = self.post_day("clear")
        self.assertIsNone(r.json()["status"])
        self.assertFalse(
            DayOverride.objects.filter(date=DAY, company=self.company).exists()
        )

    def test_non_admin_with_all_perms_gets_403(self):
        user = make_manager_user(company=self.company)
        login_as(self.client, user, company=self.company)
        self.assertEqual(self.post_day("closed").status_code, 403)
        self.assertEqual(DayOverride.objects.count(), 0)

    def test_admin_missing_a_required_perm_gets_403(self):
        admin = make_company_admin(
            "admin",
            self.company,
            perms=("view_shift",),
        )
        login_as(self.client, admin, company=self.company)
        self.assertEqual(self.post_day("closed").status_code, 403)

    def test_admin_of_one_company_cannot_act_in_another(self):
        # Admin of A but only a member of B, with B as the session
        # company. Django perms are global, so is_company_admin is the
        # only thing stopping this.
        other = make_company("B")
        admin = make_company_admin("admin", self.company)
        CompanyMembership.objects.create(
            user=admin, company=other, role="member", status="active"
        )
        login_as(self.client, admin, company=other)

        self.assertEqual(self.post_day("closed").status_code, 403)
        self.assertEqual(DayOverride.objects.count(), 0)

    def test_writes_are_scoped_to_session_company(self):
        other = make_company("B")
        DayOverride.objects.create(date=DAY, company=other, status="holiday")
        admin = make_company_admin("admin", self.company)
        login_as(self.client, admin, company=self.company)

        self.post_day("clear")
        self.assertTrue(DayOverride.objects.filter(company=other, date=DAY).exists())

    def test_clear_leaves_team_scoped_rows_alone(self):
        team = Team.objects.create(
            company=self.company, name="Reception"
        )  # adjust fields
        DayOverride.objects.create(
            date=DAY, company=self.company, team=team, status="closed"
        )
        admin = make_company_admin("admin", self.company)
        login_as(self.client, admin, company=self.company)

        self.post_day("clear")
        self.assertEqual(DayOverride.objects.filter(team=team).count(), 1)

    def test_unknown_action_is_422(self):
        admin = make_company_admin("admin", self.company)
        login_as(self.client, admin, company=self.company)
        self.assertEqual(self.post_day("nuke").status_code, 422)

    def test_unauthenticated_is_rejected(self):
        self.assertIn(self.post_day("closed").status_code, (401, 403))


class OverrideAuthzOrderTests(TestCase):
    """authz must run before any lookup, so a caller who isn't allowed
    can't tell real employee IDs from fake ones."""

    FAKE_ID = "00000000-0000-0000-0000-000000000000"

    def setUp(self):
        self.company = make_company("A")
        self.employee = make_employee(company=self.company)

    def post_override(self, emp_id, action="off"):
        return self.client.post(
            f"/api/v1/schedule/overrides/{emp_id}/{DAY.isoformat()}/",
            {"action": action},
            content_type="application/json",
        )

    def test_non_admin_gets_same_403_for_real_and_fake_employee(self):
        user = make_manager_user(company=self.company)
        login_as(self.client, user, company=self.company)
        for emp_id in (self.employee.pk, self.FAKE_ID):
            self.assertEqual(self.post_override(emp_id).status_code, 403)

    def test_member_without_perms_gets_403(self):
        user = make_member_user(company=self.company)
        login_as(self.client, user, company=self.company)
        self.assertEqual(self.post_override(self.employee.pk).status_code, 403)

    def test_admin_without_per_action_perm_gets_403(self):
        # delete_shift is required for "off", add_shift for "save".
        admin = make_company_admin("admin", self.company, perms=("add_shift",))
        login_as(self.client, admin, company=self.company)
        self.assertEqual(self.post_override(self.employee.pk, "off").status_code, 403)

    def test_admin_gets_404_for_other_companys_employee(self):
        other_employee = make_employee(email="x@example.com", company=make_company("B"))
        admin = make_company_admin(
            "admin",
            self.company,
            perms=("delete_shift", "view_shift"),
        )
        login_as(self.client, admin, company=self.company)
        self.assertEqual(self.post_override(other_employee.pk).status_code, 404)
