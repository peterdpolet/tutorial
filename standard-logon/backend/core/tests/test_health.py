from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase
from django.urls import reverse

from core.services import health


class HealthServiceTests(TestCase):
    """The rule, tested with no HTTP involved at all."""

    def test_reports_ok_when_the_database_answers(self):
        self.assertEqual(
            health.check_health(),
            {"status": "ok", "database": "ok"},
        )

    def test_reports_degraded_when_the_database_is_down(self):
        with patch("core.services.health.connection") as fake_connection:
            fake_connection.cursor.side_effect = DatabaseError("down")
            result = health.check_health()
        self.assertEqual(result, {"status": "degraded", "database": "unavailable"})


class HealthViewTests(TestCase):
    """The view only translates between HTTP and the service."""

    def test_returns_200_and_the_service_result(self):
        response = self.client.get(reverse("core:health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok"})

    def test_returns_503_when_the_service_reports_degraded(self):
        degraded = {"status": "degraded", "database": "unavailable"}
        with patch("core.views.health.check_health", return_value=degraded):
            response = self.client.get(reverse("core:health"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), degraded)

    def test_calls_the_service_exactly_once(self):
        ok = {"status": "ok", "database": "ok"}
        with patch("core.views.health.check_health", return_value=ok) as service:
            self.client.get(reverse("core:health"))
        service.assert_called_once_with()

    def test_rejects_post(self):
        response = self.client.post(reverse("core:health"))
        self.assertEqual(response.status_code, 405)
