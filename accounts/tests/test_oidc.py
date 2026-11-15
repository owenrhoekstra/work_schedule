from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase, override_settings

from accounts.backends import DocketOIDCBackend
from accounts.models import OIDCIdentity
from schedule.models import CompanyMembership
from schedule.tests.factories import make_company, make_employee

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}

_OIDC_SETTINGS = dict(
    OIDC_ENABLED=True,
    OIDC_RP_CLIENT_ID="test-client",
    OIDC_RP_CLIENT_SECRET="",
    OIDC_USE_PKCE=True,
    OIDC_RP_SIGN_ALGO="RS256",
    OIDC_RP_SCOPES="openid email profile",
    OIDC_OP_AUTHORIZATION_ENDPOINT="https://auth.example.com/oauth/v2/authorize",
    OIDC_OP_TOKEN_ENDPOINT="https://auth.example.com/oauth/v2/token",
    OIDC_OP_USER_ENDPOINT="https://auth.example.com/oidc/v1/userinfo",
    OIDC_OP_JWKS_ENDPOINT="https://auth.example.com/oauth/v2/keys",
    OIDC_CREATE_USER=True,
    OIDC_USERNAME_CLAIM="sub",
)


def _claims(
    email,
    given_name="A",
    family_name="B",
    sub="sub-1",
    iss="https://auth.example.com",
):
    return {
        "iss": iss,
        "sub": sub,
        "email": email,
        "email_verified": True,
        "given_name": given_name,
        "family_name": family_name,
    }


@override_settings(CACHES=_LOCMEM_CACHES, **_OIDC_SETTINGS)
class OIDCBackendTests(TestCase):
    def setUp(self):
        self.backend = DocketOIDCBackend()

    def test_filter_users_by_claims_matches_existing_identity(self):
        user = User.objects.create_user(username="u1", email="a@x.com")
        OIDCIdentity.objects.create(
            user=user, issuer="https://auth.example.com", subject="sub-1"
        )
        result = self.backend.filter_users_by_claims(_claims("a@x.com"))
        self.assertEqual(list(result), [user])

    def test_filter_users_by_claims_falls_back_to_email(self):
        user = User.objects.create_user(username="u1", email="a@x.com")
        result = self.backend.filter_users_by_claims(
            _claims("A@X.COM", sub="brand-new")
        )
        self.assertEqual(list(result), [user])

    def test_filter_users_by_claims_no_match(self):
        result = self.backend.filter_users_by_claims(_claims("missing@x.com"))
        self.assertFalse(result.exists())

    def test_create_user_links_active_unlinked_employee(self):
        company = make_company()
        emp = make_employee(email="new@x.com", company=company)
        user = self.backend.create_user(_claims("new@x.com", sub="sub-new"))

        self.assertIsNotNone(user)
        self.assertFalse(user.is_active)

        emp.refresh_from_db()
        self.assertEqual(emp.user_id, user.id)

        membership = CompanyMembership.objects.get(user=user, company=company)
        self.assertEqual(membership.status, "pending")
        self.assertTrue(
            OIDCIdentity.objects.filter(user=user, subject="sub-new").exists()
        )

    def test_create_user_refuses_when_no_employee(self):
        user = self.backend.create_user(_claims("stranger@x.com", sub="sub-x"))
        self.assertIsNone(user)

    def test_create_user_refuses_when_employee_already_linked(self):
        company = make_company()
        existing = User.objects.create_user(
            username="existing", email="taken@x.com"
        )
        make_employee(email="taken@x.com", company=company, user=existing)

        user = self.backend.create_user(_claims("taken@x.com", sub="sub-taken"))
        self.assertIsNone(user)

    def test_update_user_syncs_name_and_last_login(self):
        user = User.objects.create_user(username="u1", email="a@x.com")
        OIDCIdentity.objects.create(
            user=user, issuer="https://auth.example.com", subject="sub-1"
        )
        self.backend.update_user(
            user,
            _claims("a@x.com", given_name="New", family_name="Name"),
        )
        user.refresh_from_db()
        self.assertEqual(user.first_name, "New")
        self.assertEqual(user.last_name, "Name")
        identity = OIDCIdentity.objects.get(user=user, subject="sub-1")
        self.assertIsNotNone(identity.last_login_at)


@override_settings(CACHES=_LOCMEM_CACHES)
class OIDCContextProcessorTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().get("/")

    def test_reflects_setting_false(self):
        from accounts.context_processors import oidc_enabled

        with override_settings(OIDC_ENABLED=False):
            self.assertEqual(oidc_enabled(self.request)["oidc_enabled"], False)

    def test_reflects_setting_true(self):
        from accounts.context_processors import oidc_enabled

        with override_settings(OIDC_ENABLED=True):
            self.assertEqual(oidc_enabled(self.request)["oidc_enabled"], True)


@override_settings(CACHES=_LOCMEM_CACHES, **_OIDC_SETTINGS)
class OIDCUrlsTests(TestCase):
    def test_authentication_init_route_exists(self):
        from django.urls import reverse

        # The URL resolves; we don't follow the redirect to Zitadel.
        self.assertEqual(reverse("oidc_authentication_init"), "/oidc/authenticate/")

    def test_callback_route_exists(self):
        from django.urls import reverse

        self.assertEqual(reverse("oidc_authentication_callback"), "/oidc/callback/")