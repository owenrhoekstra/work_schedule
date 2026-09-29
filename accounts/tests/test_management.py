from io import StringIO

from axes.models import AccessAttempt, AccessLog
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings

_LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


@override_settings(CACHES=_LOCMEM_CACHES)
class ClearLockoutsCommandTests(TestCase):
    def setUp(self):
        AccessAttempt.objects.all().delete()
        AccessLog.objects.all().delete()
        User.objects.create_user(username="target", password="pass")
        # Trigger a failed login so axes creates an attempt row
        self.client.post(
            "/accounts/login/",
            {"username": "target", "password": "wrong"},
        )

    def test_clears_all_attempts(self):
        self.assertGreater(AccessAttempt.objects.count(), 0)
        call_command("clear_lockouts", stdout=StringIO())
        self.assertEqual(AccessAttempt.objects.count(), 0)

    def test_filtered_by_username_matches(self):
        call_command("clear_lockouts", "--username=target", stdout=StringIO())
        self.assertEqual(AccessAttempt.objects.filter(username="target").count(), 0)

    def test_filtered_by_username_no_match_keeps_rows(self):
        call_command("clear_lockouts", "--username=nobody", stdout=StringIO())
        self.assertEqual(AccessAttempt.objects.filter(username="target").count(), 1)

    def test_filtered_by_ip(self):
        attempt = AccessAttempt.objects.first()
        call_command("clear_lockouts", f"--ip={attempt.ip_address}", stdout=StringIO())
        self.assertEqual(AccessAttempt.objects.count(), 0)

    def test_output_reports_count(self):
        out = StringIO()
        call_command("clear_lockouts", stdout=out)
        self.assertIn("Cleared", out.getvalue())
