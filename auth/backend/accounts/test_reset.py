"""
Episode 6 tests. Each name says which step of the Password-reset flow it protects.

Run:  python manage.py test accounts.test_reset -v 2
"""
import json
import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from tracker.models import RuntimeEvent, TraceRun

from .models import LoginLock, ResetToken
from .test_login import EMAIL, GOOD_PASSWORD, login, make_user
from .test_refresh import refresh
from .tokens import hash_secret
from .views import FORGOT_REPLY

User = get_user_model()

FORGOT = "/api/auth/forgot/"
RESET = "/api/auth/reset/"
NEW_PASSWORD = "a-brand-new-password-9"
OTHER_NEW_PASSWORD = "another-new-password-7"


def forgot(client, email=EMAIL, **extra):
    return client.post(FORGOT, data=json.dumps({"email": email}), content_type="application/json", **extra)


def reset(client, token, password=NEW_PASSWORD, **extra):
    return client.post(RESET, data=json.dumps({"token": token, "password": password}),
                       content_type="application/json", **extra)


def token_in(message):
    """The secret in the emailed link: .../reset?token=SECRET"""
    return re.search(r"/reset\?token=([\w-]+)", message.body).group(1)


def age(minutes):
    """Make every reset link look `minutes` older."""
    ResetToken.objects.update(created_at=timezone.now() - timedelta(minutes=minutes))


class ResetTestCase(TestCase):
    """One person with two logins (laptop and phone), and another person."""

    def setUp(self):
        make_user()
        self.laptop = login(self.client).json()
        self.phone = login(self.client).json()
        make_user("other@example.com")
        self.other = login(self.client, email="other@example.com").json()

    def request_link(self, email=EMAIL):
        forgot(self.client, email=email)
        return token_in(mail.outbox[-1])


class AskForALinkHappyPathTests(ResetTestCase):
    def test_forgot_answers_200_with_the_standard_words(self):
        resp = forgot(self.client)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"detail": FORGOT_REPLY})

    def test_one_email_goes_to_the_account(self):                           # step 5
        forgot(self.client)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [EMAIL])
        self.assertIn("/reset?token=", mail.outbox[0].body)

    def test_only_a_hash_of_the_link_is_stored(self):                       # step 4
        token = self.request_link()
        row = ResetToken.objects.get()
        self.assertNotEqual(row.token_hash, token)
        self.assertEqual(row.token_hash, hash_secret(token))

    def test_the_address_is_tidied_like_everywhere_else(self):              # step 1
        forgot(self.client, email="  Learner@Example.COM ")
        self.assertEqual(len(mail.outbox), 1)

    def test_a_newer_link_retires_the_older_one(self):                      # step 4
        first = self.request_link()
        age(5)                                                              # past the cooldown
        second = self.request_link()
        self.assertEqual(reset(self.client, first).status_code, 400)
        self.assertEqual(reset(self.client, second).status_code, 200)


class AskForALinkUnhappyPathTests(ResetTestCase):
    def test_an_unknown_address_gets_the_same_reply_and_no_email(self):     # step 2
        known = forgot(self.client)
        mail.outbox.clear()
        unknown = forgot(self.client, email="nobody@example.com")
        self.assertEqual(unknown.status_code, known.status_code)
        self.assertEqual(unknown.json(), known.json())
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(ResetToken.objects.filter(user__username="nobody@example.com").count(), 0)

    def test_an_unconfirmed_account_gets_the_same_reply_and_no_email(self):   # step 2
        make_user("new@example.com", active=False)
        resp = forgot(self.client, email="new@example.com")
        self.assertEqual(resp.json(), {"detail": FORGOT_REPLY})
        self.assertEqual(len(mail.outbox), 0)

    def test_a_second_request_inside_the_cooldown_sends_nothing(self):      # step 3
        forgot(self.client)
        resp = forgot(self.client)
        self.assertEqual(resp.json(), {"detail": FORGOT_REPLY})             # still the same words
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(ResetToken.objects.count(), 1)

    def test_after_the_cooldown_a_new_link_is_sent(self):                   # step 3
        forgot(self.client)
        age(5)
        forgot(self.client)
        self.assertEqual(len(mail.outbox), 2)

    def test_missing_email(self):
        resp = self.client.post(FORGOT, data="{}", content_type="application/json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("email", resp.json()["errors"])

    def test_body_that_is_not_json(self):
        self.assertEqual(self.client.post(FORGOT, data="nope", content_type="application/json").status_code, 400)

    def test_only_post_is_allowed(self):
        self.assertEqual(self.client.get(FORGOT).status_code, 405)


class UseTheLinkHappyPathTests(ResetTestCase):
    def test_reset_answers_200_and_does_not_log_the_person_in(self):
        resp = reset(self.client, self.request_link())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"detail": "Password changed. Log in with your new password."})

    def test_the_new_password_works_and_the_old_one_does_not(self):         # step 5
        reset(self.client, self.request_link())
        self.assertEqual(login(self.client, password=GOOD_PASSWORD).status_code, 401)
        self.assertEqual(login(self.client, password=NEW_PASSWORD).status_code, 200)

    def test_reset_ends_every_login_of_the_person(self):                    # step 5 (the planted bug)
        reset(self.client, self.request_link())
        self.assertEqual(refresh(self.client, self.laptop["refresh_token"]).status_code, 401)
        self.assertEqual(refresh(self.client, self.phone["refresh_token"]).status_code, 401)

    def test_reset_leaves_other_peoples_logins_alone(self):                 # step 5
        reset(self.client, self.request_link())
        self.assertEqual(refresh(self.client, self.other["refresh_token"]).status_code, 200)

    def test_reset_clears_a_lockout(self):                                  # step 5
        for _ in range(5):
            login(self.client, password="wrong-password-1")
        self.assertEqual(login(self.client, password=GOOD_PASSWORD).status_code, 429)  # locked, even with the right password
        reset(self.client, self.request_link())
        self.assertEqual(login(self.client, password=NEW_PASSWORD).status_code, 200)
        self.assertEqual(LoginLock.objects.get(email=EMAIL).failed_count, 0)

    def test_a_link_just_inside_its_lifetime_still_works(self):             # step 3
        token = self.request_link()
        age(59)
        self.assertEqual(reset(self.client, token).status_code, 200)


class UseTheLinkUnhappyPathTests(ResetTestCase):
    def test_a_made_up_link_is_refused(self):                               # step 1
        resp = reset(self.client, "not-a-real-link")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["errors"]["token"], ["This reset link is not valid."])

    def test_a_link_works_once(self):                                       # step 2
        token = self.request_link()
        self.assertEqual(reset(self.client, token).status_code, 200)
        resp = reset(self.client, token, password=OTHER_NEW_PASSWORD)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["errors"]["token"], ["This reset link has already been used."])
        self.assertEqual(login(self.client, password=NEW_PASSWORD).status_code, 200)         # unchanged
        self.assertEqual(login(self.client, password=OTHER_NEW_PASSWORD).status_code, 401)

    def test_an_expired_link_is_refused_and_changes_nothing(self):          # step 3
        token = self.request_link()
        age(61)
        resp = reset(self.client, token)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["errors"]["token"], ["This reset link has expired. Ask for a new one."])
        self.assertEqual(login(self.client, password=GOOD_PASSWORD).status_code, 200)        # still the old one

    def test_a_weak_password_is_refused_with_the_reasons(self):             # step 4
        resp = reset(self.client, self.request_link(), password="short")
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(resp.json()["errors"]["password"])

    def test_a_password_like_the_email_is_refused(self):                    # step 4
        resp = reset(self.client, self.request_link(), password=EMAIL)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("password", resp.json()["errors"])

    def test_a_weak_password_does_not_use_up_the_link(self):                # step 4
        token = self.request_link()
        reset(self.client, token, password="short")
        self.assertIsNone(ResetToken.objects.get().used_at)
        self.assertEqual(reset(self.client, token).status_code, 200)        # same link, better password

    def test_a_weak_password_changes_nothing_else(self):                    # step 4
        reset(self.client, self.request_link(), password="short")
        self.assertEqual(login(self.client, password=GOOD_PASSWORD).status_code, 200)
        self.assertEqual(refresh(self.client, self.phone["refresh_token"]).status_code, 200)

    def test_a_link_for_an_account_since_deactivated_is_refused(self):      # step 1
        token = self.request_link()
        User.objects.filter(username=EMAIL).update(is_active=False)
        self.assertEqual(reset(self.client, token).status_code, 400)


class UseTheLinkBadRequestTests(TestCase):
    def test_missing_token_and_password(self):
        resp = self.client.post(RESET, data="{}", content_type="application/json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(set(resp.json()["errors"]), {"token", "password"})

    def test_body_that_is_not_json(self):
        self.assertEqual(self.client.post(RESET, data="nope", content_type="application/json").status_code, 400)

    def test_only_post_is_allowed(self):
        self.assertEqual(self.client.get(RESET).status_code, 405)


# Django's test runner switches DEBUG off, and the development tracing rule
# only works while DEBUG is on, so these tests turn it back on.
@override_settings(DEBUG=True)
class TracingTests(ResetTestCase):
    def labels(self):
        return list(RuntimeEvent.objects.filter(event_type="checkpoint").order_by("seq").values_list("label", flat=True))

    def calls(self):
        return set(RuntimeEvent.objects.filter(event_type="call").values_list("qualname", flat=True))

    def value(self, label, key):
        values = RuntimeEvent.objects.get(label=label).values_json
        values = values if isinstance(values, dict) else json.loads(values)
        return str(values[key])

    def test_asking_for_a_link_shows_the_steps_and_decisions(self):
        forgot(self.client, HTTP_X_TRACKER="1")
        self.assertEqual(self.calls(), {
            "forgot_view", "request_reset", "normalise_email", "find_account",
            "check_cooldown", "issue_reset_token", "send_reset_email"})
        self.assertEqual(self.labels(), ["account_lookup", "cooldown_check", "reset_issued", "email_sent"])

    def test_an_unknown_address_stops_after_the_lookup(self):
        forgot(self.client, email="nobody@example.com", HTTP_X_TRACKER="1")
        self.assertEqual(self.labels(), ["account_lookup"])
        self.assertEqual(self.value("account_lookup", "found"), "False")

    def test_the_cooldown_stops_a_second_email_and_the_trace_says_why(self):
        forgot(self.client)
        forgot(self.client, HTTP_X_TRACKER="1")
        self.assertEqual(self.labels(), ["account_lookup", "cooldown_check"])
        self.assertEqual(self.value("cooldown_check", "too_soon"), "True")

    def test_using_the_link_shows_every_step(self):
        token = self.request_link()
        reset(self.client, token, HTTP_X_TRACKER="1")
        self.assertEqual(self.calls(), {
            "reset_view", "reset_password", "find_reset", "check_reset_not_used",
            "check_reset_not_expired", "check_new_password", "apply_reset",
            "end_all_logins", "reset_failures"})
        self.assertEqual(self.labels(), [
            "reset_lookup", "used_check", "expiry_check", "password_accepted",
            "link_claimed", "password_changed", "all_logins_ended", "failures_reset"])

    def test_the_trace_counts_the_logins_that_were_ended(self):
        reset(self.client, self.request_link(), HTTP_X_TRACKER="1")
        self.assertEqual(self.value("all_logins_ended", "revoked_rows"), "2")   # laptop and phone

    def test_a_weak_password_stops_before_the_link_is_claimed(self):
        reset(self.client, self.request_link(), password="short", HTTP_X_TRACKER="1")
        self.assertEqual(self.labels(), ["reset_lookup", "used_check", "expiry_check", "password_refused"])

    def test_redaction_audit_no_secret_is_stored(self):
        token = self.request_link()
        forgot(self.client, HTTP_X_TRACKER="1")
        reset(self.client, token, HTTP_X_TRACKER="1")
        reset(self.client, "not-a-real-link", password=OTHER_NEW_PASSWORD, HTTP_X_TRACKER="1")
        self.assertEqual(TraceRun.objects.count(), 3)
        self.assertGreater(RuntimeEvent.objects.count(), 0)          # an empty trace would pass vacuously
        stored = json.dumps(
            list(RuntimeEvent.objects.values(
                "qualname", "label", "args_json", "return_repr", "exception_repr", "values_json"))
            + list(TraceRun.objects.values("path", "method")),
            default=str,
        )
        for secret in (token, "not-a-real-link", NEW_PASSWORD, OTHER_NEW_PASSWORD, GOOD_PASSWORD, EMAIL,
                       self.laptop["refresh_token"], self.laptop["access_token"], self.phone["refresh_token"]):
            self.assertNotIn(secret, stored, f"{secret!r} leaked into the stored trace")
