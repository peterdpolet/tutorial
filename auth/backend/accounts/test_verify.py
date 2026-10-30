"""
Episode 2 tests. Each test name says which step of the Verify flow it protects.

Run:  python manage.py test accounts
"""
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from tracker.models import RuntimeEvent, TraceRun

from .models import EmailToken
from .tests import GOOD_PASSWORD, post

User = get_user_model()

VERIFY_URL = "/api/auth/verify/"


def verify(client, token, **extra):
    return client.post(VERIFY_URL, data=json.dumps({"token": token}), content_type="application/json", **extra)


class VerifyTestCase(TestCase):
    """Starts each test with one registered, not-yet-verified account."""

    def setUp(self):
        post(self.client, {"email": "learner@example.com", "password": GOOD_PASSWORD})
        self.row = EmailToken.objects.get()
        self.user = User.objects.get(username="learner@example.com")

    def age(self, **delta):
        EmailToken.objects.filter(pk=self.row.pk).update(created_at=timezone.now() - timedelta(**delta))


class HappyPathTests(VerifyTestCase):
    def test_the_link_in_the_email_switches_the_account_on(self):
        self.assertFalse(self.user.is_active)
        token = mail.outbox[0].body.split("token=")[1].split()[0]
        resp = verify(self.client, token)
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)                       # step 4

    def test_the_link_is_marked_used(self):
        verify(self.client, self.row.token)
        self.row.refresh_from_db()
        self.assertIsNotNone(self.row.used_at)                     # step 4

    def test_a_link_just_inside_the_limit_still_works(self):
        self.age(hours=23, minutes=59)                             # step 3
        self.assertEqual(verify(self.client, self.row.token).status_code, 200)


class UnhappyPathExpiredTests(VerifyTestCase):
    def test_a_link_just_past_the_limit_is_refused(self):          # step 3
        self.age(hours=24, minutes=1)
        resp = verify(self.client, self.row.token)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("expired", resp.json()["errors"]["token"][0])

    def test_a_link_two_days_and_an_hour_old_is_refused(self):     # step 3 (the planted bug)
        self.age(days=2, hours=1)
        resp = verify(self.client, self.row.token)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("expired", resp.json()["errors"]["token"][0])

    def test_an_expired_link_leaves_the_account_off_and_the_link_unused(self):
        self.age(days=3)
        verify(self.client, self.row.token)
        self.user.refresh_from_db()
        self.row.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertIsNone(self.row.used_at)


class UnhappyPathUsedTwiceTests(VerifyTestCase):
    def test_the_same_link_twice_is_refused_the_second_time(self):   # step 2
        self.assertEqual(verify(self.client, self.row.token).status_code, 200)
        resp = verify(self.client, self.row.token)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("already been used", resp.json()["errors"]["token"][0])

    def test_two_clicks_at_once_only_one_wins(self):                 # step 4
        # Simulate the race: both requests passed the "not used" check, then
        # the first one claims the link before the second tries to.
        from .verify import VerificationError, activate_and_consume

        activate_and_consume(row=self.row)
        with self.assertRaises(VerificationError):
            activate_and_consume(row=self.row)


class UnhappyPathBadRequestTests(VerifyTestCase):
    def test_a_made_up_token_is_refused(self):                       # step 1
        resp = verify(self.client, "not-a-real-token")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("not valid", resp.json()["errors"]["token"][0])
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_missing_token(self):
        resp = self.client.post(VERIFY_URL, data="{}", content_type="application/json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("token", resp.json()["errors"])

    def test_only_post_is_allowed(self):
        self.assertEqual(self.client.get(VERIFY_URL).status_code, 405)

    @override_settings(EMAIL_TOKEN_LIFETIME_HOURS=1)
    def test_the_limit_comes_from_settings(self):
        self.age(hours=2)
        self.assertEqual(verify(self.client, self.row.token).status_code, 400)


@override_settings(DEBUG=True)
class TracingTests(VerifyTestCase):
    def traced_verify(self):
        return verify(self.client, self.row.token, HTTP_X_TRACKER="1")

    def test_a_verify_request_is_traced_step_by_step(self):
        self.traced_verify()
        run = TraceRun.objects.get(path=VERIFY_URL)
        names = set(
            RuntimeEvent.objects.filter(transaction_id=str(run.pk), event_type="call").values_list("qualname", flat=True)
        )
        self.assertEqual(
            names,
            {"verify_view", "verify_email", "find_token", "check_not_used", "check_not_expired", "activate_and_consume"},
        )

    def test_the_trace_shows_the_decisions(self):
        self.traced_verify()
        run = TraceRun.objects.get(path=VERIFY_URL)
        labels = list(
            RuntimeEvent.objects.filter(transaction_id=str(run.pk), event_type="checkpoint")
            .order_by("seq")
            .values_list("label", flat=True)
        )
        self.assertEqual(labels, ["token_lookup", "used_check", "expiry_check", "link_claimed", "user_activated"])

    def test_the_expiry_decision_is_visible_with_its_numbers(self):
        self.age(hours=30)
        self.traced_verify()
        run = TraceRun.objects.get(path=VERIFY_URL)
        cp = RuntimeEvent.objects.get(transaction_id=str(run.pk), label="expiry_check")
        self.assertEqual(cp.values_json["expired"], "True")
        self.assertEqual(cp.values_json["limit_hours"], "24")

    def test_redaction_audit_the_token_is_never_stored(self):
        self.traced_verify()
        run = TraceRun.objects.get(path=VERIFY_URL)
        events = RuntimeEvent.objects.filter(transaction_id=str(run.pk))
        self.assertGreater(events.count(), 0)                        # an empty trace would pass vacuously
        stored = json.dumps(
            list(events.values("qualname", "label", "args_json", "return_repr", "exception_repr", "values_json"))
            + list(TraceRun.objects.values("path", "method")),
            default=str,
        )
        for secret in (self.row.token, "learner@example.com", GOOD_PASSWORD):
            self.assertNotIn(secret, stored, f"{secret!r} leaked into the stored trace")
