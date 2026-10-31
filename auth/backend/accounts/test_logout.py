"""
Episode 5 tests. Each name says which step of the Logout flow it protects.

Run:  python manage.py test accounts.test_logout -v 2
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from tracker.models import RuntimeEvent, TraceRun

from .models import RefreshToken
from .test_login import EMAIL, GOOD_PASSWORD, login, make_user
from .test_refresh import ME, refresh

User = get_user_model()

URL = "/api/auth/logout/"


def logout(client, refresh_token, everywhere=None, **extra):
    payload = {"refresh_token": refresh_token}
    if everywhere is not None:
        payload["everywhere"] = everywhere
    return client.post(URL, data=json.dumps(payload), content_type="application/json", **extra)


class LogoutTestCase(TestCase):
    """One person with two logins (say, a laptop and a phone), and another person."""

    def setUp(self):
        make_user()
        self.laptop = login(self.client).json()
        self.phone = login(self.client).json()
        make_user("other@example.com")
        self.other = login(self.client, email="other@example.com").json()


class HappyPathTests(LogoutTestCase):
    def test_logout_answers_200(self):
        resp = logout(self.client, self.laptop["refresh_token"])
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"detail": "Logged out."})

    def test_after_logout_the_refresh_token_no_longer_works(self):          # step 2
        logout(self.client, self.laptop["refresh_token"])
        self.assertEqual(refresh(self.client, self.laptop["refresh_token"]).status_code, 401)

    def test_logout_ends_the_whole_family_not_just_the_token_presented(self):    # step 2
        newest = refresh(self.client, self.laptop["refresh_token"]).json()      # the first token is now retired
        logout(self.client, self.laptop["refresh_token"])                       # logout with the OLD one
        self.assertEqual(refresh(self.client, newest["refresh_token"]).status_code, 401)

    def test_logging_out_one_login_leaves_the_persons_other_login_alone(self):  # step 2 (the planted bug)
        logout(self.client, self.laptop["refresh_token"])
        self.assertEqual(refresh(self.client, self.phone["refresh_token"]).status_code, 200)

    def test_logging_out_leaves_other_people_alone(self):                       # step 2
        logout(self.client, self.laptop["refresh_token"])
        self.assertEqual(refresh(self.client, self.other["refresh_token"]).status_code, 200)

    def test_the_person_can_log_in_again_afterwards(self):
        logout(self.client, self.laptop["refresh_token"])
        self.assertEqual(login(self.client).status_code, 200)

    def test_the_access_token_still_works_until_it_expires(self):
        # A known limit, written down as a test so nobody is surprised: the server
        # does not look access tokens up, so logout cannot recall one.
        logout(self.client, self.laptop["refresh_token"])
        resp = self.client.get(ME, HTTP_AUTHORIZATION=f"Bearer {self.laptop['access_token']}")
        self.assertEqual(resp.status_code, 200)


class LogoutEverywhereTests(LogoutTestCase):
    def test_everywhere_ends_every_login_of_the_person(self):                   # step 2
        logout(self.client, self.laptop["refresh_token"], everywhere=True)
        self.assertEqual(refresh(self.client, self.laptop["refresh_token"]).status_code, 401)
        self.assertEqual(refresh(self.client, self.phone["refresh_token"]).status_code, 401)

    def test_everywhere_still_leaves_other_people_alone(self):                  # step 2
        logout(self.client, self.laptop["refresh_token"], everywhere=True)
        self.assertEqual(refresh(self.client, self.other["refresh_token"]).status_code, 200)

    def test_only_a_real_true_means_everywhere(self):                           # not the string "true"
        logout(self.client, self.laptop["refresh_token"], everywhere="true")
        self.assertEqual(refresh(self.client, self.phone["refresh_token"]).status_code, 200)


class UnhappyPathUnknownOrRepeatedTests(LogoutTestCase):
    def test_an_unknown_token_is_still_a_success_and_changes_nothing(self):     # step 1
        live_before = RefreshToken.objects.filter(revoked_at__isnull=True).count()
        resp = logout(self.client, "not-a-real-token")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(RefreshToken.objects.filter(revoked_at__isnull=True).count(), live_before)

    def test_logging_out_twice_is_fine(self):                                   # step 1
        self.assertEqual(logout(self.client, self.laptop["refresh_token"]).status_code, 200)
        self.assertEqual(logout(self.client, self.laptop["refresh_token"]).status_code, 200)

    def test_a_deactivated_account_can_still_log_out(self):                     # nothing to block it
        User.objects.filter(username=EMAIL).update(is_active=False)
        self.assertEqual(logout(self.client, self.laptop["refresh_token"]).status_code, 200)


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
class TracingTests(LogoutTestCase):
    def labels(self):
        return list(RuntimeEvent.objects.filter(event_type="checkpoint").order_by("seq").values_list("label", flat=True))

    def revoked_rows(self, label):
        values = RuntimeEvent.objects.get(label=label).values_json
        values = values if isinstance(values, dict) else json.loads(values)
        return str(values["revoked_rows"])

    def test_the_trace_shows_the_steps_and_decisions(self):
        logout(self.client, self.laptop["refresh_token"], HTTP_X_TRACKER="1")
        names = set(RuntimeEvent.objects.filter(event_type="call").values_list("qualname", flat=True))
        self.assertEqual(names, {"logout_view", "logout", "find_logout_session", "end_login"})
        self.assertEqual(self.labels(), ["logout_lookup", "login_ended"])

    def test_the_trace_counts_what_was_ended(self):
        logout(self.client, self.laptop["refresh_token"], HTTP_X_TRACKER="1")
        self.assertEqual(self.revoked_rows("login_ended"), "1")      # this login's one live token, no more

    def test_everywhere_shows_in_the_trace(self):
        logout(self.client, self.laptop["refresh_token"], everywhere=True, HTTP_X_TRACKER="1")
        self.assertEqual(self.labels(), ["logout_lookup", "all_logins_ended"])
        self.assertEqual(self.revoked_rows("all_logins_ended"), "2")  # laptop and phone

    def test_an_unknown_token_stops_after_the_lookup(self):
        logout(self.client, "not-a-real-token", HTTP_X_TRACKER="1")
        self.assertEqual(self.labels(), ["logout_lookup"])

    def test_redaction_audit_no_token_is_stored(self):
        logout(self.client, self.laptop["refresh_token"], HTTP_X_TRACKER="1")
        logout(self.client, "not-a-real-token", HTTP_X_TRACKER="1")
        self.assertEqual(TraceRun.objects.count(), 2)
        self.assertGreater(RuntimeEvent.objects.count(), 0)          # an empty trace would pass vacuously
        stored = json.dumps(
            list(RuntimeEvent.objects.values(
                "qualname", "label", "args_json", "return_repr", "exception_repr", "values_json"))
            + list(TraceRun.objects.values("path", "method")),
            default=str,
        )
        for secret in (self.laptop["refresh_token"], self.laptop["access_token"],
                       self.phone["refresh_token"], "not-a-real-token", EMAIL, GOOD_PASSWORD):
            self.assertNotIn(secret, stored, f"{secret!r} leaked into the stored trace")
