"""
Episode 4 tests. Each name says which step of the Refresh flow it protects.

Run:  python manage.py test accounts.test_refresh -v 2
"""
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from tracker.models import RuntimeEvent, TraceRun

from .models import RefreshToken
from .test_login import EMAIL, GOOD_PASSWORD, login, make_user
from .tokens import hash_refresh_token

User = get_user_model()

URL = "/api/auth/refresh/"
ME = "/api/auth/me/"


def refresh(client, refresh_token, **extra):
    return client.post(URL, data=json.dumps({"refresh_token": refresh_token}),
                       content_type="application/json", **extra)


class RefreshTestCase(TestCase):
    """Starts every test with one logged-in user holding a first token pair."""

    def setUp(self):
        make_user()
        self.first = login(self.client).json()


class HappyPathTests(RefreshTestCase):
    def test_refresh_returns_a_new_pair(self):                       # step 5
        resp = refresh(self.client, self.first["refresh_token"])
        self.assertEqual(resp.status_code, 200)
        new = resp.json()
        self.assertEqual(set(new), {"access_token", "refresh_token", "expires_in"})
        # The refresh token is random, so it always changes. (The access token is
        # a signed "user, time" note with no random part, so two made in the same
        # second are identical; that is harmless, so it is not asserted.)
        self.assertNotEqual(new["refresh_token"], self.first["refresh_token"])

    def test_the_new_access_token_opens_me(self):                    # step 5
        new = refresh(self.client, self.first["refresh_token"]).json()
        resp = self.client.get(ME, HTTP_AUTHORIZATION=f"Bearer {new['access_token']}")
        self.assertEqual(resp.json(), {"email": EMAIL})

    def test_the_old_token_is_retired_and_the_new_one_joins_its_family(self):    # step 5
        refresh(self.client, self.first["refresh_token"])
        old = RefreshToken.objects.get(token_hash=hash_refresh_token(self.first["refresh_token"]))
        self.assertIsNotNone(old.revoked_at)
        live = RefreshToken.objects.get(revoked_at__isnull=True)
        self.assertEqual(live.family, old.family)

    def test_a_chain_of_refreshes_keeps_working(self):               # step 5
        token = self.first["refresh_token"]
        for _ in range(3):
            resp = refresh(self.client, token)
            self.assertEqual(resp.status_code, 200)
            token = resp.json()["refresh_token"]
        self.assertEqual(RefreshToken.objects.count(), 4)
        self.assertEqual(RefreshToken.objects.filter(revoked_at__isnull=True).count(), 1)

    def test_only_a_hash_of_the_new_token_is_stored(self):           # step 5
        new = refresh(self.client, self.first["refresh_token"]).json()
        hashes = set(RefreshToken.objects.values_list("token_hash", flat=True))
        self.assertIn(hash_refresh_token(new["refresh_token"]), hashes)
        self.assertNotIn(new["refresh_token"], hashes)


class UnhappyPathUnknownOrExpiredTests(RefreshTestCase):
    def test_a_made_up_token_is_refused(self):                       # step 1
        resp = refresh(self.client, "not-a-real-token")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(RefreshToken.objects.count(), 1)            # nothing issued

    def test_an_expired_token_is_refused_and_nothing_is_issued(self):    # step 3
        RefreshToken.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        resp = refresh(self.client, self.first["refresh_token"])
        self.assertEqual(resp.status_code, 401)
        self.assertIn("expired", resp.json()["detail"])
        self.assertEqual(RefreshToken.objects.count(), 1)

    def test_a_token_that_expires_in_a_minute_still_works(self):     # step 3 (boundary)
        RefreshToken.objects.update(expires_at=timezone.now() + timedelta(minutes=1))
        self.assertEqual(refresh(self.client, self.first["refresh_token"]).status_code, 200)

    def test_a_deactivated_account_cannot_refresh(self):             # step 4
        User.objects.update(is_active=False)
        resp = refresh(self.client, self.first["refresh_token"])
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(RefreshToken.objects.count(), 1)


class UnhappyPathReplayTests(RefreshTestCase):
    """The reason for rotation: a retired token coming back means a copy exists."""

    def setUp(self):
        super().setUp()
        self.second = refresh(self.client, self.first["refresh_token"]).json()

    def test_a_retired_token_is_refused(self):                       # step 2
        resp = refresh(self.client, self.first["refresh_token"])
        self.assertEqual(resp.status_code, 401)
        self.assertIn("ended", resp.json()["detail"])

    def test_replaying_a_retired_token_ends_the_whole_login(self):   # step 2 (the planted bug)
        refresh(self.client, self.first["refresh_token"])            # the thief (or the owner) is second
        self.assertFalse(RefreshToken.objects.filter(revoked_at__isnull=True).exists())
        resp = refresh(self.client, self.second["refresh_token"])    # the newest token is dead too
        self.assertEqual(resp.status_code, 401)

    def test_a_replay_issues_nothing(self):                          # step 2
        before = RefreshToken.objects.count()
        refresh(self.client, self.first["refresh_token"])
        self.assertEqual(RefreshToken.objects.count(), before)

    def test_another_login_by_the_same_person_is_not_affected(self):    # families are separate
        other = login(self.client).json()
        refresh(self.client, self.first["refresh_token"])            # replay ends the first family
        self.assertEqual(refresh(self.client, other["refresh_token"]).status_code, 200)

    def test_the_same_token_cannot_be_spent_twice(self):             # step 5 (the claim)
        token = self.second["refresh_token"]
        self.assertEqual(refresh(self.client, token).status_code, 200)
        self.assertEqual(refresh(self.client, token).status_code, 401)


class UnhappyPathBadRequestTests(TestCase):
    def test_missing_token(self):
        resp = self.client.post(URL, data="{}", content_type="application/json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("refresh_token", resp.json()["errors"])

    def test_body_that_is_not_json(self):
        resp = self.client.post(URL, data="nope", content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_only_post_is_allowed(self):
        self.assertEqual(self.client.get(URL).status_code, 405)


# Django's test runner switches DEBUG off, and the development tracing rule
# only works while DEBUG is on, so these tests turn it back on.
@override_settings(DEBUG=True)
class TracingTests(RefreshTestCase):
    def labels(self):
        return list(RuntimeEvent.objects.filter(event_type="checkpoint").order_by("seq").values_list("label", flat=True))

    def test_the_trace_shows_the_steps_and_decisions(self):
        refresh(self.client, self.first["refresh_token"], HTTP_X_TRACKER="1")
        names = set(RuntimeEvent.objects.filter(event_type="call").values_list("qualname", flat=True))
        self.assertEqual(
            names,
            {"refresh_view", "refresh", "find_refresh_token", "check_not_replayed",
             "check_refresh_not_expired", "check_user_active", "rotate_tokens"},
        )
        self.assertEqual(
            self.labels(),
            ["refresh_lookup", "replay_check", "refresh_expiry_check", "user_active_check",
             "token_claimed", "tokens_rotated"],
        )

    def test_a_replay_shows_the_family_being_ended_with_a_count(self):
        refresh(self.client, self.first["refresh_token"])            # the first spend: fine
        refresh(self.client, self.first["refresh_token"], HTTP_X_TRACKER="1")   # the replay, traced
        self.assertEqual(self.labels(), ["refresh_lookup", "replay_check", "family_revoked"])
        event = RuntimeEvent.objects.get(label="family_revoked")
        values = event.values_json if isinstance(event.values_json, dict) else json.loads(event.values_json)
        self.assertEqual(str(values["revoked_rows"]), "1")                  # the one live token (the newest) was ended

    def test_redaction_audit_no_token_is_stored(self):
        second = refresh(self.client, self.first["refresh_token"], HTTP_X_TRACKER="1").json()
        refresh(self.client, self.first["refresh_token"], HTTP_X_TRACKER="1")      # a replay, traced too
        self.assertEqual(TraceRun.objects.count(), 2)
        self.assertGreater(RuntimeEvent.objects.count(), 0)          # an empty trace would pass vacuously
        stored = json.dumps(
            list(RuntimeEvent.objects.values(
                "qualname", "label", "args_json", "return_repr", "exception_repr", "values_json"))
            + list(TraceRun.objects.values("path", "method")),
            default=str,
        )
        for secret in (self.first["refresh_token"], self.first["access_token"],
                       second["refresh_token"], second["access_token"], EMAIL, GOOD_PASSWORD):
            self.assertNotIn(secret, stored, f"{secret!r} leaked into the stored trace")
