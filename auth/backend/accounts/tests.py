"""
Episode 1 tests. Each test name says which step of the Register flow it
protects, so a failing name points straight at the step on the process map.

Run:  python manage.py test accounts
"""
import json

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings

from tracker.models import RuntimeEvent, TraceRun

from .models import EmailToken

User = get_user_model()

URL = "/api/auth/register/"
GOOD_PASSWORD = "Tut0rial-Pass!"   # invented; only ever used in this tutorial


def post(client, payload, **extra):
    return client.post(URL, data=json.dumps(payload), content_type="application/json", **extra)


class HappyPathTests(TestCase):
    def test_register_creates_an_inactive_user(self):
        resp = post(self.client, {"email": "learner@example.com", "password": GOOD_PASSWORD})
        self.assertEqual(resp.status_code, 201)
        user = User.objects.get(username="learner@example.com")
        self.assertFalse(user.is_active)                       # step 4
        self.assertNotEqual(user.password, GOOD_PASSWORD)      # stored hashed
        self.assertTrue(user.check_password(GOOD_PASSWORD))

    def test_register_issues_one_token_and_sends_one_email(self):
        post(self.client, {"email": "learner@example.com", "password": GOOD_PASSWORD})
        token = EmailToken.objects.get()                       # step 5
        self.assertIsNone(token.used_at)
        self.assertEqual(len(mail.outbox), 1)                  # step 6
        self.assertEqual(mail.outbox[0].to, ["learner@example.com"])
        self.assertIn(f"/verify?token={token.token}", mail.outbox[0].body)

    def test_surrounding_spaces_are_removed_from_the_email(self):   # step 1
        post(self.client, {"email": "  learner@example.com ", "password": GOOD_PASSWORD})
        self.assertTrue(User.objects.filter(username="learner@example.com").exists())


class UnhappyPathEmailAlreadyRegisteredTests(TestCase):
    def setUp(self):
        post(self.client, {"email": "learner@example.com", "password": GOOD_PASSWORD})

    def test_same_email_again_is_refused(self):                # step 2
        resp = post(self.client, {"email": "learner@example.com", "password": GOOD_PASSWORD})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("already registered", resp.json()["errors"]["email"][0])
        self.assertEqual(User.objects.count(), 1)

    def test_same_email_in_other_capitals_is_also_refused(self):   # step 2 (the planted bug)
        resp = post(self.client, {"email": "Learner@Example.com", "password": GOOD_PASSWORD})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(User.objects.count(), 1)

    def test_a_refused_duplicate_sends_no_second_email(self):
        post(self.client, {"email": "learner@example.com", "password": GOOD_PASSWORD})
        self.assertEqual(len(mail.outbox), 1)


class UnhappyPathWeakPasswordTests(TestCase):
    def test_common_password_is_refused_and_nothing_is_saved(self):    # step 3
        resp = post(self.client, {"email": "learner@example.com", "password": "password123"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("password", resp.json()["errors"])
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_short_password_says_why(self):
        resp = post(self.client, {"email": "learner@example.com", "password": "Ab1!"})
        self.assertIn("too short", resp.json()["errors"]["password"][0])


class UnhappyPathBadRequestTests(TestCase):
    def test_invalid_email(self):                              # step 1
        resp = post(self.client, {"email": "not-an-email", "password": GOOD_PASSWORD})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("email", resp.json()["errors"])

    def test_missing_fields(self):
        resp = post(self.client, {})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(set(resp.json()["errors"]), {"email", "password"})

    def test_body_that_is_not_json(self):
        resp = self.client.post(URL, data="nope", content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_only_post_is_allowed(self):
        self.assertEqual(self.client.get(URL).status_code, 405)


# Django's test runner switches DEBUG off, and the development tracing rule
# only works while DEBUG is on, so these tests turn it back on.
@override_settings(DEBUG=True)
class TracingTests(TestCase):
    """Register is used by people who are not logged in, so these tests prove
    the development tracing rule works for it AND that no secret reaches the
    stored trace."""

    @override_settings(DEBUG=False)
    def test_with_debug_off_an_anonymous_request_is_not_traced(self):
        self.traced_register()
        self.assertEqual(TraceRun.objects.count(), 0)

    def traced_register(self):
        return post(
            self.client,
            {"email": "learner@example.com", "password": GOOD_PASSWORD},
            HTTP_X_TRACKER="1",
        )

    def test_an_anonymous_register_request_is_traced(self):
        resp = self.traced_register()
        run = TraceRun.objects.get()
        self.assertEqual(resp["X-Tracker-Run"], str(run.pk))
        names = set(RuntimeEvent.objects.filter(event_type="call").values_list("qualname", flat=True))
        self.assertEqual(
            names,
            {"register_view", "register", "clean_email", "check_email_free", "check_password",
             "create_inactive_user", "issue_verification_token", "send_verification_email"},
        )

    def test_without_the_header_nothing_is_traced(self):
        post(self.client, {"email": "learner@example.com", "password": GOOD_PASSWORD})
        self.assertEqual(TraceRun.objects.count(), 0)

    def test_the_trace_shows_the_decisions(self):
        self.traced_register()
        labels = list(
            RuntimeEvent.objects.filter(event_type="checkpoint").order_by("seq").values_list("label", flat=True)
        )
        self.assertEqual(
            labels,
            ["duplicate_check", "password_accepted", "user_created", "token_issued", "email_sent"],
        )

    def test_redaction_audit_no_secret_is_stored(self):
        self.traced_register()
        token = EmailToken.objects.get().token
        self.assertGreater(RuntimeEvent.objects.count(), 0)   # an empty trace would pass vacuously
        stored = json.dumps(
            list(
                RuntimeEvent.objects.values(
                    "qualname", "label", "args_json", "return_repr", "exception_repr", "values_json"
                )
            )
            + list(TraceRun.objects.values("path", "method")),
            default=str,
        )
        for secret in (GOOD_PASSWORD, "Tut0rial", "learner@example.com", token):
            self.assertNotIn(secret, stored, f"{secret!r} leaked into the stored trace")


class ShowTraceCommandTests(TestCase):
    @override_settings(DEBUG=True)
    def test_prints_the_latest_trace_as_a_tree(self):
        from io import StringIO

        from django.core.management import call_command

        post(self.client, {"email": "learner@example.com", "password": GOOD_PASSWORD}, HTTP_X_TRACKER="1")
        out = StringIO()
        call_command("show_trace", stdout=out)
        text = out.getvalue()
        self.assertIn("POST /api/auth/register/  ->  201", text)
        self.assertIn("check_email_free", text)
        self.assertIn(". duplicate_check", text)
        self.assertNotIn(GOOD_PASSWORD, text)

    def test_says_so_when_there_is_nothing_to_show(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("show_trace")
