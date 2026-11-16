"""Tests for GET /api/v1/me/.

Django's test client against the mounted URL — exercises the full
middleware chain (TenantMiddleware resolution, deactivation) and
Ninja's session_auth. A bare ninja.testing.TestClient call would
bypass the middleware, which is precisely what we want covered.

TenantMiddleware already exempts /api/v1/ (see
_TENANT_EXEMPT_PREFIXES); test_no_viable_memberships and
test_stale_session_company pin the behavior that depends on it.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from schedule.models import Team, TeamMembership
from schedule.tests._helpers import login_as
from schedule.tests.factories import (
    make_company,
    make_management_user,
    make_manager_user,
)

User = get_user_model()


class MeEndpointTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.user = make_management_user(company=self.company)
        self.user.first_name = "Ada"
        self.user.last_name = "Lovelace"
        self.user.save()

    def test_anonymous_returns_401(self):
        response = self.client.get("/api/v1/me/")
        self.assertEqual(response.status_code, 401)

    def test_returns_identity_memberships_and_permissions(self):
        login_as(self.client, self.user, self.company)

        response = self.client.get("/api/v1/me/")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["id"], str(self.user.id))
        self.assertEqual(data["first_name"], "Ada")
        self.assertEqual(data["last_name"], "Lovelace")
        self.assertTrue(data["is_platform_admin"])
        self.assertIn("schedule.view_shift", data["permissions"])
        self.assertEqual(data["current_company_id"], str(self.company.id))
        self.assertIsNone(data["current_team_id"])

        self.assertEqual(len(data["companies"]), 1)
        company = data["companies"][0]
        self.assertEqual(company["id"], str(self.company.id))
        self.assertEqual(company["name"], self.company.name)
        self.assertEqual(company["slug"], self.company.slug)
        self.assertEqual(company["role"], "admin")
        self.assertEqual(data["teams"], [])

    def test_no_viable_memberships_returns_empty_payload(self):
        # Contract: 200 + empty so the SPA can redirect to /accounts/waiting/.
        # Depends on TenantMiddleware exempting /api/v1/ — without it the
        # request 302s to the picker before reaching the view.
        lonely = User.objects.create_user(
            username="lonely", password="x", first_name="L", last_name="One"
        )
        self.client.force_login(lonely)

        response = self.client.get("/api/v1/me/")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["first_name"], "L")
        self.assertFalse(data["is_platform_admin"])
        self.assertIsNone(data["current_company_id"])
        self.assertIsNone(data["current_team_id"])
        self.assertEqual(data["companies"], [])
        self.assertEqual(data["teams"], [])

    def test_stale_session_company_returns_null(self):
        # Non-platform-admin: session points at a company the user has
        # no viable membership in. Middleware clears the stale session
        # and refuses to auto-substitute (matches the "open form for old
        # company must not silently target new company" rule).
        other = make_company(name="Other", slug="other-co")
        manager = make_manager_user(company=self.company)
        login_as(self.client, manager, other)

        response = self.client.get("/api/v1/me/")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIsNone(data["current_company_id"])
        self.assertEqual(len(data["companies"]), 1)
        self.assertEqual(data["companies"][0]["id"], str(self.company.id))

    def test_platform_admin_current_company_may_not_be_in_companies(self):
        # Platform admins can reach any company via middleware's fast
        # path, even one they have no membership at. Endpoint reports
        # current_company_id truthfully; companies[] stays membership-
        # scoped. If these ever silently realign, we've lost the
        # platform-admin reach guarantee.
        other = make_company(name="Other", slug="other-co")
        # self.user is a platform admin (make_management_user).
        login_as(self.client, self.user, other)

        response = self.client.get("/api/v1/me/")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["current_company_id"], str(other.id))
        company_ids = [c["id"] for c in data["companies"]]
        self.assertNotIn(str(other.id), company_ids)

    def test_team_membership_and_current_team_id(self):

        team = Team.objects.create(company=self.company, name="Kitchen")
        TeamMembership.objects.create(
            user=self.user, team=team, role="admin", valid_from=date.today()
        )

        login_as(self.client, self.user, self.company, team=team)

        data = self.client.get("/api/v1/me/").json()
        self.assertEqual(data["current_team_id"], str(team.id))
        self.assertEqual(len(data["teams"]), 1)
        membership = data["teams"][0]
        self.assertEqual(membership["id"], str(team.id))
        self.assertEqual(membership["name"], team.name)
        self.assertEqual(membership["company_id"], str(self.company.id))
        self.assertEqual(membership["role"], "admin")
