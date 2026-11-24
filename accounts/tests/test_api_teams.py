"""Tests for POST /api/v1/teams/select/."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from schedule.models import (
    CompanyMembership,
    Team,
    TeamMembership,
)
from schedule.tests._helpers import login_as
from schedule.tests.factories import (
    make_company,
    make_employee,
    make_management_user,
    make_member_user,
)

User = get_user_model()


class SelectTeamEndpointTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.other_company = make_company(name="Other", slug="other-co")
        self.admin = make_management_user(company=self.company)
        self.team_a = Team.objects.create(
            company=self.company, name="Kitchen", allow_member_view_all=True
        )
        self.team_b = Team.objects.create(
            company=self.company, name="Front House", allow_member_view_all=True
        )
        TeamMembership.objects.create(
            user=self.admin,
            team=self.team_a,
            role="admin",
            valid_from=timezone.localdate(),
        )
        TeamMembership.objects.create(
            user=self.admin,
            team=self.team_b,
            role="admin",
            valid_from=timezone.localdate(),
        )

    def _url(self):
        return "/api/v1/teams/select/"

    def _post(self, team_id):
        return self.client.post(
            self._url(),
            data={"team_id": team_id},
            content_type="application/json",
        )

    def test_anonymous_returns_401(self):
        response = self.client.post(
            self._url(),
            data={"team_id": str(self.team_a.id)},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_selecting_valid_team_sets_session(self):
        login_as(self.client, self.admin, self.company)
        response = self._post(str(self.team_a.id))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(self.client.session["team_id"], str(self.team_a.id))

    def test_selecting_null_clears_session(self):
        login_as(self.client, self.admin, self.company)
        self.client.session["team_id"] = str(self.team_a.id)
        self.client.session.save()
        response = self._post(None)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("team_id", self.client.session)

    def test_selecting_empty_string_clears_session(self):
        login_as(self.client, self.admin, self.company)
        self.client.session["team_id"] = str(self.team_a.id)
        self.client.session.save()
        response = self._post("")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("team_id", self.client.session)

    def test_team_in_other_company_rejected(self):
        other_team = Team.objects.create(
            company=self.other_company, name="Kitchen", allow_member_view_all=True
        )
        login_as(self.client, self.admin, self.company)
        response = self._post(str(other_team.id))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["ok"])

    def test_team_not_viewable_rejected(self):
        # Plain member with no EmployeeTeam, team flag false →
        # not viewable as team scope.
        locked = Team.objects.create(
            company=self.company, name="Locked", allow_member_view_all=False
        )
        user = make_member_user(company=self.company, username="plain")
        make_employee(company=self.company, user=user, email="p@x.com")
        login_as(self.client, user, self.company)
        response = self._post(str(locked.id))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["ok"])

    def test_invalid_uuid_rejected(self):
        login_as(self.client, self.admin, self.company)
        response = self._post("not-a-uuid")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["ok"])

    def test_company_switch_clears_team_selection(self):
        # Set team, then switch company; team_id must be cleared.
        second_company = make_company(name="Second", slug="second-co")
        CompanyMembership.objects.create(
            user=self.admin, company=second_company, role="admin", status="active"
        )
        login_as(self.client, self.admin, self.company)
        self.client.session["team_id"] = str(self.team_a.id)
        self.client.session.save()

        # Switch company
        response = self.client.post(
            "/api/v1/companies/select/",
            data={"company_id": str(second_company.id)},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertNotIn("team_id", self.client.session)

    def test_selecting_same_company_preserves_team(self):
        login_as(self.client, self.admin, self.company)

        session = self.client.session
        session["company_id"] = str(self.company.id)
        session["team_id"] = str(self.team_a.id)
        session.save()

        response = self.client.post(
            "/api/v1/companies/select/",
            data={"company_id": str(self.company.id)},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session.get("team_id"), str(self.team_a.id))
