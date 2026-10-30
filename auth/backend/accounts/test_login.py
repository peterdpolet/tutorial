"""
Episode 3 tests. Each name says which step of the Login flow it protects.

Run:  python manage.py test accounts.test_login
"""
import hashlib
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from tracker.models import RuntimeEvent, TraceRun

from .models import LoginLock, RefreshToken
from .tests import GOOD_PASSWORD

User = get_user_model()

URL = "/api/auth/login/"
ME = "/api/auth/me/"
EMAIL = "learner@example.com"
BAD_LOGIN = "Email or password is incorrect."


def login(client, email=EMAIL, password=GOOD_PASSWORD, **extra):
    return client.post(URL, data=json.dumps({"email": email, "password": password}),
                       content_type="application/json", **extra)


def make_user(email=EMAIL, active=True):
    user = User.objects.create_user(username=email, email=email, password=GOOD_PASSWORD)
    user.is_active = active
    user.save(update_fields=["is_active"])
    return user


class HappyPathTests(TestCase):
    def setUp(self):
        make_user()

    def test_login_returns_both_tokens(self):                       # step 6
        resp = login(self.client)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(set(body), {"access_token", "refresh_token", "expires_in"})
        self.assertEqual(body["expires_in"], 900)

    def test_the_access_token_opens_me(self):
        token = login(self.client).json()["access_token"]
        resp = self.client.get(ME, HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"email": EMAIL})

    def test_only_a_hash_of_the_refresh_token_is_stored(self):      # step 6
        refresh = login(self.client).json()["refresh_token"]
        row = RefreshToken.objects.get()
        self.assertNotEqual(row.token_hash, refresh)
        self.assertEqual(row.token_hash, hashlib.sha256(refresh.encode()).hexdigest())
        self.assertGreater(row.expires_at, timezone.now() + timedelta(days=13))

    def test_capitals_and_spaces_in_the_email_do_not_matter(self):  # step 1
        self.assertEqual(login(self.client, email="  Learner@Example.COM ").status_code, 200)

    def test_a_good_login_wipes_earlier_failures(self):             # step 5 (the planted bug)
        for _ in range(4):
            login(self.client, password="wrong-one")
        self.assertEqual(login(self.client).status_code, 200)
        self.assertEqual(LoginLock.objects.get(email=EMAIL).failed_count, 0)
        for _ in range(4):                                           # four more would be eight in all
            self.assertEqual(login(self.client, password="wrong-one").status_code, 401)
        self.assertEqual(login(self.client).status_code, 200)        # still not locked


class UnhappyPathWrongCredentialsTests(TestCase):
    def setUp(self):
        make_user()

    def test_wrong_password_is_refused_with_no_tokens(self):        # step 3
        resp = login(self.client, password="not-the-password")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json(), {"detail": BAD_LOGIN})
        self.assertEqual(RefreshToken.objects.count(), 0)

    def test_unknown_email_gets_exactly_the_same_reply(self):       # step 3
        wrong = login(self.client, password="not-the-password")
        unknown = login(self.client, email="nobody@example.com")
        self.assertEqual(unknown.status_code, wrong.status_code)
        self.assertEqual(unknown.json(), wrong.json())

    def test_unverified_account_with_the_right_password_is_told_to_confirm(self):   # step 4
        make_user("new@example.com", active=False)
        resp = login(self.client, email="new@example.com")
        self.assertEqual(resp.status_code, 403)
        self.assertIn("Confirm your email", resp.json()["detail"])
        self.assertEqual(RefreshToken.objects.count(), 0)

    def test_unverified_account_with_the_wrong_password_learns_nothing(self):    # step 3 before 4
        make_user("new@example.com", active=False)
        resp = login(self.client, email="new@example.com", password="not-the-password")
        self.assertEqual(resp.json(), {"detail": BAD_LOGIN})


class UnhappyPathLockoutTests(TestCase):
    def setUp(self):
        make_user()

    def fail_times(self, n, email=EMAIL):
        for _ in range(n):
            login(self.client, email=email, password="wrong-one")

    def test_five_failures_lock_the_address(self):                  # step 2
        self.fail_times(5)
        resp = login(self.client)                                    # the RIGHT password now
        self.assertEqual(resp.status_code, 429)
        self.assertIn("Too many failed attempts", resp.json()["detail"])
        self.assertEqual(RefreshToken.objects.count(), 0)

    def test_four_failures_do_not_lock(self):                       # step 2
        self.fail_times(4)
        self.assertEqual(login(self.client).status_code, 200)

    def test_an_address_with_no_account_locks_the_same_way(self):   # no leak of who has an account
        self.fail_times(5, email="nobody@example.com")
        resp = login(self.client, email="nobody@example.com")
        self.assertEqual(resp.status_code, 429)

    def test_the_lock_ends(self):                                   # step 2
        self.fail_times(5)
        LoginLock.objects.update(locked_until=timezone.now() - timedelta(seconds=1))
        self.assertEqual(login(self.client).status_code, 200)

    def test_attempts_while_locked_do_not_extend_the_lock(self):    # step 2
        self.fail_times(5)
        until = LoginLock.objects.get().locked_until
        self.fail_times(3)
        self.assertEqual(LoginLock.objects.get().locked_until, until)


class UnhappyPathBadRequestTests(TestCase):
    def test_missing_fields(self):
        resp = self.client.post(URL, data="{}", content_type="application/json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(set(resp.json()["errors"]), {"email", "password"})

    def test_body_that_is_not_json(self):
        resp = self.client.post(URL, data="nope", content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_only_post_is_allowed(self):
        self.assertEqual(self.client.get(URL).status_code, 405)


class AccessTokenTests(TestCase):
    def setUp(self):
        make_user()
        self.token = login(self.client).json()["access_token"]

    def me(self, header):
        return self.client.get(ME, HTTP_AUTHORIZATION=header) if header else self.client.get(ME)

    def test_no_header(self):
        self.assertEqual(self.me(None).status_code, 401)

    def test_a_tampered_token(self):
        self.assertEqual(self.me(f"Bearer {self.token}x").status_code, 401)

    def test_an_expired_token(self):
        with override_settings(ACCESS_TOKEN_SECONDS=-1):
            resp = self.me(f"Bearer {self.token}")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("expired", resp.json()["detail"])

    def test_a_deactivated_account_loses_access(self):
        User.objects.update(is_active=False)
        self.assertEqual(self.me(f"Bearer {self.token}").status_code, 401)


# Django's test runner switches DEBUG off, and the development tracing rule
# only works while DEBUG is on, so these tests turn it back on.
@override_settings(DEBUG=True)
class TracingTests(TestCase):
    def setUp(self):
        make_user()

    def test_the_trace_shows_the_steps_and_decisions(self):
        login(self.client, HTTP_X_TRACKER="1")
        names = set(RuntimeEvent.objects.filter(event_type="call").values_list("qualname", flat=True))
        self.assertEqual(
            names,
            {"login_view", "login", "normalise_email", "check_not_locked", "check_credentials",
             "check_active", "reset_failures", "issue_tokens"},
        )
        labels = list(RuntimeEvent.objects.filter(event_type="checkpoint").order_by("seq").values_list("label", flat=True))
        self.assertEqual(
            labels,
            ["lock_check", "credentials_check", "active_check", "failures_reset", "tokens_issued"],
        )

    def test_a_refused_login_records_the_failure(self):
        login(self.client, password="wrong-one", HTTP_X_TRACKER="1")
        labels = list(RuntimeEvent.objects.filter(event_type="checkpoint").order_by("seq").values_list("label", flat=True))
        self.assertEqual(labels, ["lock_check", "credentials_check", "failure_recorded"])

    def test_redaction_audit_no_secret_is_stored(self):
        body = login(self.client, HTTP_X_TRACKER="1").json()
        me = self.client.get(ME, HTTP_AUTHORIZATION=f"Bearer {body['access_token']}", HTTP_X_TRACKER="1")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(TraceRun.objects.count(), 2)
        self.assertGreater(RuntimeEvent.objects.count(), 0)         # an empty trace would pass vacuously
        stored = json.dumps(
            list(RuntimeEvent.objects.values(
                "qualname", "label", "args_json", "return_repr", "exception_repr", "values_json"))
            + list(TraceRun.objects.values("path", "method")),
            default=str,
        )
        for secret in (GOOD_PASSWORD, "Tut0rial", EMAIL, body["access_token"], body["refresh_token"]):
            self.assertNotIn(secret, stored, f"{secret!r} leaked into the stored trace")
