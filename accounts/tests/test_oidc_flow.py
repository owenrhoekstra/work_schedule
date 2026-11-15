"""End-to-end OIDC flow tests.

Mocks at the network and crypto boundaries (token exchange via
requests.post, JWT verification via verify_token, userinfo via
get_userinfo), then lets the real mozilla-django-oidc view, our
DocketOIDCBackend, and session handling run end-to-end.

We deliberately do NOT rebuild a real RS256 JWT + JWKS: that's the
library's responsibility. Our code is the flow logic — state check,
user resolution, pending membership creation. Mock verify_token and
get_userinfo and the tests exercise exactly our logic.

Note: setting OIDC_OP_USER_ENDPOINT="" does NOT skip the userinfo
fetch in this library version — requests.get("") raises
MissingSchema. The mock is what bypasses it.
"""

from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import OIDCIdentity
from schedule.models import CompanyMembership, Employee
from schedule.tests._helpers import login_as
from schedule.tests.factories import (
    make_company,
    make_employee,
    make_superuser,
)

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}

_ISSUER = "https://auth.example.com"


def _claims(email, sub="sub-1", given_name="A", family_name="B"):
    return {
        "iss": _ISSUER,
        "sub": sub,
        "email": email,
        "email_verified": True,
        "given_name": given_name,
        "family_name": family_name,
    }


_OIDC_SETTINGS = dict(
    OIDC_ENABLED=True,
    OIDC_RP_CLIENT_ID="test-client",
    OIDC_RP_CLIENT_SECRET="",
    OIDC_USE_PKCE=True,
    OIDC_RP_SIGN_ALGO="RS256",
    OIDC_RP_SCOPES="openid email profile",
    OIDC_OP_ISSUER=_ISSUER,
    OIDC_OP_AUTHORIZATION_ENDPOINT=f"{_ISSUER}/oauth/v2/authorize",
    OIDC_OP_TOKEN_ENDPOINT=f"{_ISSUER}/oauth/v2/token",
    OIDC_OP_USER_ENDPOINT=f"{_ISSUER}/oidc/v1/userinfo",
    OIDC_OP_JWKS_ENDPOINT=f"{_ISSUER}/oauth/v2/keys",
    OIDC_CREATE_USER=True,
    OIDC_USERNAME_CLAIM="sub",
)


@override_settings(CACHES=_LOCMEM_CACHES, **_OIDC_SETTINGS)
class OIDCAuthenticateRedirectTests(TestCase):
    def test_redirects_to_zitadel_with_pkce_params(self):
        resp = self.client.get(reverse("oidc_authentication_init"))
        self.assertEqual(resp.status_code, 302)

        parsed = urlparse(resp.url)
        qs = parse_qs(parsed.query)
        self.assertEqual(parsed.netloc, "auth.example.com")
        self.assertEqual(parsed.path, "/oauth/v2/authorize")
        self.assertEqual(qs["response_type"], ["code"])
        self.assertEqual(qs["client_id"], ["test-client"])
        self.assertEqual(qs["code_challenge_method"], ["S256"])
        self.assertIn("code_challenge", qs)
        self.assertIn("state", qs)
        self.assertIn("nonce", qs)
        # PKCE: no client secret in the redirect
        self.assertNotIn("client_secret", qs)

    def test_next_param_stored_in_session(self):
        self.client.get(
            reverse("oidc_authentication_init") + "?next=/accounts/waiting/"
        )
        # Whatever key the library uses, the next URL round-trips.
        self.assertEqual(
            self.client.session.get("oidc_login_next"), "/accounts/waiting/"
        )


@override_settings(CACHES=_LOCMEM_CACHES, **_OIDC_SETTINGS)
class OIDCCallbackFlowTests(TestCase):
    def setUp(self):
        self.company = make_company()

        # Token exchange (backend.authenticate POSTs to OIDC_OP_TOKEN_ENDPOINT)
        self.mock_post = patch("mozilla_django_oidc.auth.requests.post").start()
        self.addCleanup(patch.stopall)

        # JWT verification — bypassed. Library's crypto, not our logic.
        self.mock_verify = patch(
            "mozilla_django_oidc.auth.OIDCAuthenticationBackend.verify_token"
        ).start()
        self.addCleanup(patch.stopall)

        # Userinfo — mocked to return the claims dict directly. Setting
        # OIDC_OP_USER_ENDPOINT="" does not skip the network call in
        # this library version, so we mock the method itself.
        self.mock_userinfo = patch(
            "mozilla_django_oidc.auth.OIDCAuthenticationBackend.get_userinfo"
        ).start()
        self.addCleanup(patch.stopall)

    def _run_flow(self, claims, next_url=None, state_override=None):
        init_url = reverse("oidc_authentication_init")
        if next_url:
            init_url += f"?next={next_url}"
        init_resp = self.client.get(init_url)
        state = state_override or parse_qs(urlparse(init_resp.url).query)["state"][0]

        self.mock_verify.return_value = claims
        self.mock_userinfo.return_value = claims
        self.mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "id_token": "fake-id-token",
                "access_token": "fake-access-token",
                "token_type": "Bearer",
            },
        )

        return self.client.get(
            reverse("oidc_authentication_callback"),
            {"code": "fake-code", "state": state},
        )

    def test_first_time_login_creates_active_user_pending_membership(self):
        email = "new-oidc@example.com"
        make_employee(email=email, company=self.company)

        resp = self._run_flow(
            _claims(email, sub="sub-new"), next_url="/accounts/waiting/"
        )

        self.assertEqual(resp.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

        user = User.objects.get(email=email)
        self.assertTrue(user.is_active)

        emp = Employee.objects.get(email=email)
        self.assertEqual(emp.user_id, user.id)

        membership = CompanyMembership.objects.get(user=user)
        self.assertEqual(membership.status, "pending")

        self.assertTrue(
            OIDCIdentity.objects.filter(user=user, subject="sub-new").exists()
        )

    def test_existing_user_matched_by_email(self):
        email = "existing@example.com"
        user = User.objects.create_user(
            username="existing", email=email, is_active=True
        )
        CompanyMembership.objects.create(
            user=user, company=self.company, role="member", status="active"
        )

        self._run_flow(_claims(email, sub="sub-existing"))

        self.assertIn("_auth_user_id", self.client.session)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        self.assertTrue(
            OIDCIdentity.objects.filter(user=user, subject="sub-existing").exists()
        )

    def test_existing_oidc_identity_logs_in(self):
        email = "already@example.com"
        user = User.objects.create_user(username="already", email=email, is_active=True)
        OIDCIdentity.objects.create(user=user, issuer=_ISSUER, subject="sub-known")
        CompanyMembership.objects.create(
            user=user, company=self.company, role="member", status="active"
        )

        self._run_flow(_claims(email, sub="sub-known"))

        self.assertIn("_auth_user_id", self.client.session)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_stranger_refused(self):
        resp = self._run_flow(_claims("stranger@example.com", sub="sub-stranger"))

        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertFalse(User.objects.filter(email="stranger@example.com").exists())
        self.assertEqual(resp.status_code, 302)

    def test_state_mismatch_rejected(self):
        """The library raises SuspiciousOperation on state mismatch,
        which Django turns into a 400. That's the correct defensive
        behavior — a forged callback should fail loudly, not silently
        redirect. Assert both the 400 and that no session was created."""
        self.client.get(reverse("oidc_authentication_init"))

        resp = self.client.get(
            reverse("oidc_authentication_callback"),
            {"code": "fake-code", "state": "wrong-state"},
        )

        self.assertEqual(resp.status_code, 400)
        self.assertNotIn("_auth_user_id", self.client.session)


@override_settings(CACHES=_LOCMEM_CACHES, **_OIDC_SETTINGS)
class OIDCApprovalActivatesMembershipTests(TestCase):
    """approve_account is @permission_required("auth.change_user"). The
    standard make_management_user grants only schedule.* perms; use a
    superuser for these tests since that's the shape that hits the
    pending-approval page in production."""

    def setUp(self):
        self.company = make_company()
        self.admin = make_superuser(company=self.company)
        login_as(self.client, self.admin, self.company)

    def test_approve_flips_pending_membership_to_active(self):
        email = "pending@example.com"
        user = User.objects.create_user(username="pending", email=email, is_active=True)
        membership = CompanyMembership.objects.create(
            user=user, company=self.company, role="member", status="pending"
        )

        resp = self.client.post(reverse("approve_account", args=[user.pk]))

        self.assertEqual(resp.status_code, 302)
        membership.refresh_from_db()
        self.assertEqual(membership.status, "active")

    def test_approve_no_pending_membership_is_safe(self):
        user = User.objects.create_user(
            username="nopending", email="nopending@example.com", is_active=False
        )
        resp = self.client.post(reverse("approve_account", args=[user.pk]))
        self.assertEqual(resp.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
