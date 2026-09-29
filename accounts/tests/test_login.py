from django.test import TestCase, override_settings
from django.urls import reverse

from .factories import make_superuser

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


@override_settings(CACHES=_LOCMEM_CACHES)
class LoginViewTests(TestCase):
    def setUp(self):
        self.user = make_superuser("admin")
        # clear any axes state from prior tests
        from axes.models import AccessAttempt

        AccessAttempt.objects.all().delete()

    def test_login_page_renders(self):
        self.assertEqual(self.client.get(reverse("login")).status_code, 200)

    def test_valid_login_redirects(self):
        resp = self.client.post(
            reverse("login"),
            {"username": "admin", "password": "pass"},
        )
        self.assertEqual(resp.status_code, 302)

    def test_invalid_login_stays_on_page(self):
        resp = self.client.post(
            reverse("login"),
            {"username": "admin", "password": "wrong"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.wsgi_request.user.is_authenticated)

    def test_logout_redirects(self):
        self.client.force_login(self.user)
        resp = self.client.post(reverse("logout"))
        self.assertEqual(resp.status_code, 302)
