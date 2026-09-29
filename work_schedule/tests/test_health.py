from unittest.mock import patch

from django.test import TestCase


class HealthzTests(TestCase):
    def test_returns_ok_when_healthy(self):
        resp = self.client.get("/healthz/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b"ok")

    def test_returns_500_when_db_unavailable(self):
        with patch("work_schedule.views.connection") as mock_conn:
            mock_conn.cursor.side_effect = Exception("nope")
            resp = self.client.get("/healthz/")
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.content, b"db unavailable")

    def test_no_auth_required(self):
        resp = self.client.get("/healthz/")
        self.assertEqual(resp.status_code, 200)
