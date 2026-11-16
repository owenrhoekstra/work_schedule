"""Login API endpoint tests.

The endpoint wraps django.contrib.auth.authenticate() and returns
JSON. Axes interaction is tested separately (accounts.tests.
test_login); this file covers the API surface itself: success,
failure modes, session establishment, CSRF enforcement.
"""

import json

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


@override_settings(CACHES=_LOCMEM_CACHES)
class LoginAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="alice", password="pass", email="alice@example.com"
        )
        self.url = "/api/v1/accounts/login/"

    def _post(self, data):
        return self.client.post(
            self.url, data=json.dumps(data), content_type="application/json"
        )

    def test_valid_credentials_returns_redirect_and_session(self):
        resp = self._post({"username": "alice", "password": "pass"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["redirect_url"], "/schedule/home/")
        self.assertIn("_auth_user_id", self.client.session)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_invalid_credentials_no_session(self):
        resp = self._post({"username": "alice", "password": "wrong"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["ok"])
        self.assertIn("Invalid", data["error"])
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unknown_username_no_session(self):
        resp = self._post({"username": "nobody", "password": "pass"})
        data = resp.json()
        self.assertFalse(data["ok"])
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_user_cannot_log_in(self):
        self.user.is_active = False
        self.user.save()
        resp = self._post({"username": "alice", "password": "pass"})
        data = resp.json()
        self.assertFalse(data["ok"])
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_missing_fields_returns_422(self):
        resp = self._post({"username": "alice"})
        self.assertEqual(resp.status_code, 422)

    def test_malformed_json_returns_400(self):
        resp = self.client.post(
            self.url, data="not-json", content_type="application/json"
        )
        self.assertEqual(resp.status_code, 400)

    def test_csrf_required(self):
        client = Client(enforce_csrf_checks=True)
        resp = client.post(
            self.url,
            data=json.dumps({"username": "alice", "password": "pass"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)


@override_settings(CACHES=_LOCMEM_CACHES)
class CsrfViewTests(TestCase):
    def test_get_sets_csrf_cookie(self):
        resp = self.client.get("/api/v1/csrf/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("csrftoken", resp.cookies)

    def test_post_rejected(self):
        resp = self.client.post("/api/v1/csrf/")
        self.assertEqual(resp.status_code, 405)
