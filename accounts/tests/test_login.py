"""Login page tests.

The /accounts/login/ URL now serves the Vue shell (GET-only — POST
re-renders the shell, no auth attempt). Actual password authentication
is tested at /api/v1/accounts/login/ — see accounts/tests/
test_login_api.py. This file covers the shell being served and Django's
logout flow.
"""

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


@override_settings(CACHES=_LOCMEM_CACHES)
class LoginViewTests(TestCase):
    def test_login_page_renders(self):
        """Django serves the shell HTML; Vue renders the form client-side."""
        resp = self.client.get(reverse("login"))
        self.assertEqual(resp.status_code, 200)

    def test_logout_redirects(self):
        user = User.objects.create_user(username="user", password="pass")
        self.client.force_login(user)
        resp = self.client.post(reverse("logout"))
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)
