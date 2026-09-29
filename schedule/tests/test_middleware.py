from datetime import date, timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .factories import make_employee, make_staff_user

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


@override_settings(CACHES=_LOCMEM_CACHES)
class EmployeeDeactivationMiddlewareTests(TestCase):
    def _make_emp_with_user(self, last_day):
        user = make_staff_user(f"u{timezone.now().timestamp()}")
        emp = make_employee(email=user.email)
        emp.user = user
        emp.last_day = last_day
        emp.save()
        user.is_active = True
        user.save(update_fields=["is_active"])
        return user, emp

    def test_past_last_day_kicks_user_out(self):
        user, _ = self._make_emp_with_user(timezone.localdate() - timedelta(days=1))
        self.client.force_login(user)
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_today_is_still_allowed(self):
        user, _ = self._make_emp_with_user(timezone.localdate())
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)

    def test_future_last_day_allowed(self):
        user, _ = self._make_emp_with_user(timezone.localdate() + timedelta(days=30))
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)

    def test_user_without_employee_passes_through(self):
        user = make_staff_user("noemployee")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)

    def test_anonymous_untouched(self):
        # Anonymous should redirect to login via @login_required, not the middleware
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.status_code, 302)
