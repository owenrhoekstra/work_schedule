from django.test import TestCase, override_settings
from django.urls import reverse

from .factories import make_employee, make_staff_user

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


@override_settings(CACHES=_LOCMEM_CACHES)
class ProfileViewTests(TestCase):
    def setUp(self):
        self.user = make_staff_user("alice")
        self.client.force_login(self.user)

    def test_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("profile"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("login"), resp.url)

    def test_get_renders(self):
        self.assertEqual(self.client.get(reverse("profile")).status_code, 200)

    def test_update_username(self):
        resp = self.client.post(
            reverse("profile"),
            {"username": "alice2", "first_name": "", "last_name": ""},
        )
        self.assertEqual(resp.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "alice2")

    def test_update_name_via_employee(self):
        emp = make_employee(email=self.user.email)
        emp.user = self.user
        emp.save()
        self.client.post(
            reverse("profile"),
            {"username": self.user.username, "first_name": "Alicia", "last_name": "S"},
        )
        emp.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(emp.first_name, "Alicia")
        # signal mirrors to user
        self.assertEqual(self.user.first_name, "Alicia")
