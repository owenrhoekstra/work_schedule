"""Smoke tests for the /api/v1/ foundation.

Uses Django's regular test client + force_login — this exercises
the full stack (session middleware, CsrfViewMiddleware, Ninja's
SessionAuth) rather than bypassing it with ninja.testing.TestClient.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings


User = get_user_model()

_LOCMEM_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}


def _make_user(email, is_staff=False):
    return User.objects.create_user(
        username=email,
        email=email,
        password="pw-not-used",
        is_staff=is_staff,
    )


@override_settings(CACHES=_LOCMEM_CACHES)
class SmokeEndpointTests(TestCase):
    def setUp(self):
        self.user = _make_user("smoke@example.com")

    def test_me_returns_current_user(self):
        self.client.force_login(self.user)
        response = self.client.get("/api/v1/smoke/me/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], self.user.id)
        self.assertEqual(data["email"], self.user.email)
        self.assertFalse(data["is_staff"])

    def test_me_requires_auth(self):
        response = self.client.get("/api/v1/smoke/me/")
        self.assertEqual(response.status_code, 401)


@override_settings(CACHES=_LOCMEM_CACHES)
class DocsGatingTests(TestCase):
    def test_docs_requires_staff(self):
        response = self.client.get("/api/v1/docs")
        # Anonymous → staff_member_required redirects to login.
        self.assertIn(response.status_code, (302, 403))

        non_staff = _make_user("nonstaff@example.com", is_staff=False)
        self.client.force_login(non_staff)
        response = self.client.get("/api/v1/docs")
        self.assertIn(response.status_code, (302, 403))

        staff = _make_user("staff@example.com", is_staff=True)
        self.client.force_login(staff)
        response = self.client.get("/api/v1/docs")
        self.assertEqual(response.status_code, 200)

    def test_openapi_json_requires_staff(self):
        non_staff = _make_user("nonstaff2@example.com", is_staff=False)
        self.client.force_login(non_staff)
        response = self.client.get("/api/v1/openapi.json")
        self.assertIn(response.status_code, (302, 403))

        staff = _make_user("staff2@example.com", is_staff=True)
        self.client.force_login(staff)
        response = self.client.get("/api/v1/openapi.json")
        self.assertEqual(response.status_code, 200)


@override_settings(CACHES=_LOCMEM_CACHES)
class UrlPrefixTests(TestCase):
    def test_api_v1_prefix_resolves(self):
        # /api/v1/docs is gated, but the URL must resolve (not 404).
        response = self.client.get("/api/v1/docs")
        self.assertNotEqual(response.status_code, 404)

    def test_bare_api_prefix_does_not_exist(self):
        response = self.client.get("/api/docs")
        self.assertEqual(response.status_code, 404)