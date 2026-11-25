"""Tests for GET /api/v1/schedule/week/."""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from schedule.models import (
    EmployeeTeam,
    Team,
    TeamMembership,
)
from schedule.tests._helpers import login_as
from schedule.tests.factories import (
    make_company,
    make_employee,
    make_management_user,
    make_viewer_user,
)

User = get_user_model()


def _make_employee_on_team(
    company, team, *, user=None, email, show_team_schedules=True, with_pattern=True
):
    emp = make_employee(
        company=company,
        with_pattern=with_pattern,
        email=email,
        show_team_schedules=show_team_schedules,
        user=user,
    )
    EmployeeTeam.objects.create(
        employee=emp, team=team, valid_from=timezone.localdate()
    )
    return emp


class WeekEndpointTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.admin = make_management_user(company=self.company)
        self.admin_emp = make_employee(
            company=self.company,
            user=self.admin,
            with_pattern=True,
            email="admin@x.com",
        )
        self.today = date.today()

    # ---- Auth ----------------------------------------------------------

    def test_anonymous_returns_401(self):
        response = self.client.get("/api/v1/schedule/week/")
        self.assertEqual(response.status_code, 401)

    # ---- me scope ------------------------------------------------------

    def test_me_scope_returns_self(self):
        login_as(self.client, self.admin, self.company)
        response = self.client.get("/api/v1/schedule/week/?scope=me")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["scope"], "me")
        self.assertEqual(len(data["employees"]), 1)
        self.assertEqual(data["employees"][0]["id"], str(self.admin_emp.id))

    def test_me_scope_without_employee_403(self):
        lonely = make_viewer_user(company=self.company)
        login_as(self.client, lonely, self.company)
        response = self.client.get("/api/v1/schedule/week/?scope=me")
        self.assertEqual(response.status_code, 403)

    # ---- company scope -------------------------------------------------

    def test_company_scope_by_admin_returns_all(self):
        other_emp = make_employee(
            company=self.company, with_pattern=True, email="other@x.com"
        )
        login_as(self.client, self.admin, self.company)
        response = self.client.get("/api/v1/schedule/week/?scope=company")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        ids = {e["id"] for e in data["employees"]}
        self.assertIn(str(self.admin_emp.id), ids)
        self.assertIn(str(other_emp.id), ids)

    def test_company_scope_by_member_without_flag_403(self):
        member = make_viewer_user(company=self.company)
        make_employee(
            company=self.company, user=member, with_pattern=True, email="m@x.com"
        )
        login_as(self.client, member, self.company)
        response = self.client.get("/api/v1/schedule/week/?scope=company")
        self.assertEqual(response.status_code, 403)

    def test_company_scope_by_member_with_flag_returns_all(self):
        self.company.allow_member_view_all = True
        self.company.save()
        member = make_viewer_user(company=self.company)
        emp = make_employee(
            company=self.company, user=member, with_pattern=True, email="m@x.com"
        )
        login_as(self.client, member, self.company)
        response = self.client.get("/api/v1/schedule/week/?scope=company")
        self.assertEqual(response.status_code, 200)
        ids = {e["id"] for e in response.json()["employees"]}
        self.assertIn(str(emp.id), ids)
        self.assertIn(str(self.admin_emp.id), ids)

    # ---- team scope ----------------------------------------------------

    def test_team_scope_member_with_flag_returns_team_roster(self):
        team = Team.objects.create(
            company=self.company, name="Kitchen", allow_member_view_all=True
        )
        member = make_viewer_user(company=self.company, username="kitchen-member")
        emp = _make_employee_on_team(self.company, team, user=member, email="km@x.com")
        peer = _make_employee_on_team(
            self.company,
            team,
            email="kp@x.com",
        )
        login_as(self.client, member, self.company)
        response = self.client.get("/api/v1/schedule/week/?scope=team")
        self.assertEqual(response.status_code, 200)
        ids = {e["id"] for e in response.json()["employees"]}
        self.assertIn(str(emp.id), ids)
        self.assertIn(str(peer.id), ids)
        self.assertNotIn(str(self.admin_emp.id), ids)  # not on team

    def test_team_scope_member_without_flag_403(self):
        team = Team.objects.create(
            company=self.company, name="Kitchen", allow_member_view_all=False
        )
        member = make_viewer_user(company=self.company)
        _make_employee_on_team(self.company, team, user=member, email="km@x.com")
        login_as(self.client, member, self.company)
        response = self.client.get("/api/v1/schedule/week/?scope=team")
        self.assertEqual(response.status_code, 403)

    def test_team_scope_show_team_schedules_false_403(self):
        team = Team.objects.create(
            company=self.company, name="Kitchen", allow_member_view_all=True
        )
        member = make_viewer_user(company=self.company)
        _make_employee_on_team(
            self.company,
            team,
            user=member,
            email="km@x.com",
            show_team_schedules=False,
        )
        login_as(self.client, member, self.company)
        response = self.client.get("/api/v1/schedule/week/?scope=team")
        self.assertEqual(response.status_code, 403)

    def test_team_scope_team_admin_without_flag_returns_roster(self):
        team = Team.objects.create(
            company=self.company, name="Kitchen", allow_member_view_all=False
        )
        admin_user = make_viewer_user(company=self.company, username="team-admin")
        TeamMembership.objects.create(
            user=admin_user, team=team, role="admin", valid_from=timezone.localdate()
        )
        member_emp = _make_employee_on_team(self.company, team, email="km@x.com")
        login_as(self.client, admin_user, self.company)
        response = self.client.get("/api/v1/schedule/week/?scope=team")
        self.assertEqual(response.status_code, 200)
        ids = {e["id"] for e in response.json()["employees"]}
        self.assertIn(str(member_emp.id), ids)

    def test_employee_row_includes_team_and_role(self):
        from schedule.models import EmployeeTeam, Team, TeamRole

        team = Team.objects.create(company=self.company, name="Kitchen")
        role = TeamRole.objects.create(team=team, name="Head Chef")
        EmployeeTeam.objects.create(
            employee=self.admin_emp,
            team=team,
            role=role,
            is_default=True,
            valid_from=self.today,
        )

        login_as(self.client, self.admin, self.company)
        data = self.client.get("/api/v1/schedule/week/?scope=me").json()

        row = data["employees"][0]
        self.assertEqual(row["team_name"], "Kitchen")
        self.assertEqual(row["team_role_name"], "Head Chef")

    def test_employee_without_team_has_null_team_fields(self):
        # self.admin_emp has no EmployeeTeam assignment.
        login_as(self.client, self.admin, self.company)
        data = self.client.get("/api/v1/schedule/week/?scope=me").json()
        row = data["employees"][0]
        self.assertIsNone(row["team_name"])
        self.assertIsNone(row["team_role_name"])

    # ---- shape ---------------------------------------------------------

    def test_cells_shape_and_total_minutes(self):
        login_as(self.client, self.admin, self.company)
        data = self.client.get("/api/v1/schedule/week/?scope=me").json()
        cells = data["employees"][0]["cells"]
        self.assertEqual(len(cells), 6)
        for cell in cells:
            self.assertIn(
                cell["kind"],
                {
                    "default",
                    "override",
                    "off_override",
                    "day_override",
                    "not_employed",
                    "none",
                },
            )
            self.assertIn("start", cell)
            self.assertIn("end", cell)
        # make_employee(with_pattern=True) creates an empty pattern, so
        # every cell is kind="none" and total is 0.
        self.assertEqual(data["employees"][0]["total_minutes"], 0)

    def test_week_ref_contains_navigation(self):
        login_as(self.client, self.admin, self.company)
        data = self.client.get("/api/v1/schedule/week/?scope=me").json()
        week = data["week"]
        for key in ("start", "title", "prev", "next", "is_current", "can_go_back"):
            self.assertIn(key, week)

    def test_invalid_week_400(self):
        login_as(self.client, self.admin, self.company)
        response = self.client.get("/api/v1/schedule/week/?week=not-a-date")
        self.assertEqual(response.status_code, 400)

    def test_unknown_scope_400(self):
        login_as(self.client, self.admin, self.company)
        response = self.client.get("/api/v1/schedule/week/?scope=bogus")
        self.assertEqual(response.status_code, 400)

    # ---- viewer_can ----------------------------------------------------

    def test_viewer_can_admin(self):
        login_as(self.client, self.admin, self.company)
        data = self.client.get("/api/v1/schedule/week/?scope=company").json()
        self.assertTrue(data["viewer_can"]["can_add_shift"])
        self.assertTrue(data["viewer_can"]["can_delete_shift"])
        self.assertTrue(data["viewer_can"]["change_employee_day_override"])
        self.assertTrue(data["viewer_can"]["change_day_override"])
        self.assertTrue(data["viewer_can"]["add_employee"])
        self.assertTrue(data["viewer_can"]["print"])

    def test_viewer_can_employee_all_false(self):
        member = make_viewer_user(company=self.company)
        make_employee(
            company=self.company, user=member, with_pattern=True, email="m@x.com"
        )
        login_as(self.client, member, self.company)
        data = self.client.get("/api/v1/schedule/week/?scope=me").json()
        self.assertFalse(data["viewer_can"]["can_add_shift"])
        self.assertFalse(data["viewer_can"]["can_delete_shift"])
        self.assertFalse(data["viewer_can"]["change_employee_day_override"])
        self.assertFalse(data["viewer_can"]["change_day_override"])
        self.assertFalse(data["viewer_can"]["add_employee"])
        self.assertFalse(data["viewer_can"]["print"])

    def test_team_admin_with_show_team_schedules_false_still_sees_admin_team_only(self):
        # Team A: user is admin (via TeamMembership), allow_member_view_all=False.
        # Team B: user is a member (via EmployeeTeam), allow_member_view_all=True,
        #         but their own show_team_schedules=False.
        # Expected: user sees team A's roster, NOT team B's.
        team_a = Team.objects.create(
            company=self.company, name="Admin Team", allow_member_view_all=False
        )
        team_b = Team.objects.create(
            company=self.company, name="Member Team", allow_member_view_all=True
        )
        admin_user = make_viewer_user(company=self.company, username="mixed-admin")
        TeamMembership.objects.create(
            user=admin_user, team=team_a, role="admin", valid_from=timezone.localdate()
        )
        _make_employee_on_team(
            self.company,
            team_b,
            user=admin_user,
            email="ma@x.com",
            show_team_schedules=False,
        )
        team_a_member = _make_employee_on_team(self.company, team_a, email="tam@x.com")
        team_b_peer = _make_employee_on_team(self.company, team_b, email="tbp@x.com")

        login_as(self.client, admin_user, self.company)
        response = self.client.get("/api/v1/schedule/week/?scope=team")
        self.assertEqual(response.status_code, 200)
        ids = {e["id"] for e in response.json()["employees"]}
        self.assertIn(str(team_a_member.id), ids)  # admin team visible
        self.assertNotIn(str(team_b_peer.id), ids)  # member team blocked

    def test_team_scope_scopes_to_selected_team(self):
        # Two teams, user is admin of both, session selects team A.
        # Roster must show ONLY team A's members.
        team_a = Team.objects.create(
            company=self.company, name="Kitchen", allow_member_view_all=True
        )
        team_b = Team.objects.create(
            company=self.company, name="Front", allow_member_view_all=True
        )
        member_a = _make_employee_on_team(self.company, team_a, email="a@x.com")
        member_b = _make_employee_on_team(self.company, team_b, email="b@x.com")
        TeamMembership.objects.create(
            user=self.admin, team=team_a, role="admin", valid_from=timezone.localdate()
        )
        TeamMembership.objects.create(
            user=self.admin, team=team_b, role="admin", valid_from=timezone.localdate()
        )

        login_as(self.client, self.admin, self.company, team=team_a)
        data = self.client.get("/api/v1/schedule/week/?scope=team").json()
        ids = {e["id"] for e in data["employees"]}
        self.assertIn(str(member_a.id), ids)
        self.assertNotIn(str(member_b.id), ids)

    def test_team_scope_without_session_team_returns_union(self):
        team_a = Team.objects.create(
            company=self.company, name="Kitchen", allow_member_view_all=True
        )
        team_b = Team.objects.create(
            company=self.company, name="Front", allow_member_view_all=True
        )
        member_a = _make_employee_on_team(self.company, team_a, email="a@x.com")
        member_b = _make_employee_on_team(self.company, team_b, email="b@x.com")
        TeamMembership.objects.create(
            user=self.admin, team=team_a, role="admin", valid_from=timezone.localdate()
        )
        TeamMembership.objects.create(
            user=self.admin, team=team_b, role="admin", valid_from=timezone.localdate()
        )

        login_as(self.client, self.admin, self.company)  # no team session
        data = self.client.get("/api/v1/schedule/week/?scope=team").json()
        ids = {e["id"] for e in data["employees"]}
        self.assertIn(str(member_a.id), ids)
        self.assertIn(str(member_b.id), ids)

    # sorting --------------------------------------

    def test_employees_sorted_by_start_date(self):
        # Two employees with distinct start dates; the earlier-started
        # employee sorts first, regardless of team/role. (Role-based
        # ordering is gone; Branch B replaces this with team grouping.)
        later = make_employee(
            company=self.company,
            with_pattern=True,
            email="later@x.com",
            start_date=self.today - timedelta(days=30),
        )
        earlier = make_employee(
            company=self.company,
            with_pattern=True,
            email="earlier@x.com",
            start_date=self.today - timedelta(days=90),
        )
        login_as(self.client, self.admin, self.company)
        data = self.client.get("/api/v1/schedule/week/?scope=company").json()
        ids = [e["id"] for e in data["employees"]]
        self.assertLess(ids.index(str(earlier.id)), ids.index(str(later.id)))
