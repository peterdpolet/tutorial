"""
Episode 7 tests. Each name says which step of the Two-factor flows it protects.

Run:  python manage.py test accounts.test_twofactor -v 2

The tests fix the clock: `self.step` is "now", counted in 30-second steps, and
`self.tick()` moves it on one step, as 30 seconds passing would. A real person
waits for the next code; the tests just tick.
"""
import base64
import json
import re
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings

from tracker.models import RuntimeEvent, TraceRun

from .models import LoginLock, RecoveryCode, RefreshToken, TotpDevice
from .test_login import EMAIL, GOOD_PASSWORD, ME, login, make_user
from .tokens import hash_secret
from .totp import code_for, matching_step, new_secret, provisioning_uri

User = get_user_model()

SETUP = "/api/auth/2fa/setup/"
CONFIRM = "/api/auth/2fa/confirm/"
CODE_LOGIN = "/api/auth/2fa/login/"
START = 1_000_000          # the test clock's first step


def bearer(access_token):
    return {"HTTP_AUTHORIZATION": f"Bearer {access_token}"}


def setup(client, access_token, **extra):
    return client.post(SETUP, data="{}", content_type="application/json", **bearer(access_token), **extra)


def confirm(client, access_token, code, **extra):
    return client.post(CONFIRM, data=json.dumps({"code": code}), content_type="application/json",
                       **bearer(access_token), **extra)


def code_login(client, mfa_token, code, **extra):
    return client.post(CODE_LOGIN, data=json.dumps({"mfa_token": mfa_token, "code": code}),
                       content_type="application/json", **extra)


class TotpUnitTests(SimpleTestCase):
    """The recipe itself, against the published test values (RFC 6238, appendix B, SHA-1)."""
    RFC_SECRET = base64.b32encode(b"12345678901234567890").decode()

    def test_the_standard_test_values(self):
        for seconds, expected in [(59, "94287082"), (1111111109, "07081804"), (1234567890, "89005924")]:
            self.assertEqual(code_for(self.RFC_SECRET, seconds // 30, digits=8), expected)

    def test_a_code_is_six_digits_with_leading_zeros_kept(self):
        for step in range(200):
            code = code_for(self.RFC_SECRET, step)
            self.assertEqual(len(code), 6)
            self.assertTrue(code.isdigit())

    def test_a_new_secret_is_32_letters_and_digits_for_20_random_bytes(self):
        secret = new_secret()
        self.assertEqual(len(secret), 32)
        self.assertEqual(len(base64.b32decode(secret)), 20)
        self.assertNotEqual(new_secret(), secret)

    def test_the_step_before_this_one_and_after_it_are_accepted(self):      # clocks drift
        now = 1_000_000 * 30
        for offset in (-1, 0, 1):
            code = code_for(self.RFC_SECRET, 1_000_000 + offset)
            self.assertEqual(matching_step(self.RFC_SECRET, code, after_step=0, now=now), 1_000_000 + offset)

    def test_two_steps_away_is_refused(self):
        now = 1_000_000 * 30
        for offset in (-2, 2):
            code = code_for(self.RFC_SECRET, 1_000_000 + offset)
            self.assertIsNone(matching_step(self.RFC_SECRET, code, after_step=0, now=now))

    def test_a_step_already_used_is_refused(self):                          # a code works once
        now = 1_000_000 * 30
        code = code_for(self.RFC_SECRET, 1_000_000)
        self.assertIsNone(matching_step(self.RFC_SECRET, code, after_step=1_000_000, now=now))
        self.assertIsNone(matching_step(self.RFC_SECRET, code, after_step=1_000_001, now=now))

    def test_spaces_are_ignored_but_wrong_shapes_are_not_codes(self):
        now = 1_000_000 * 30
        code = code_for(self.RFC_SECRET, 1_000_000)
        self.assertIsNotNone(matching_step(self.RFC_SECRET, f"{code[:3]} {code[3:]}", after_step=0, now=now))
        for text in ("", "12345", "1234567", "abcdef", code + "0"):
            self.assertIsNone(matching_step(self.RFC_SECRET, text, after_step=0, now=now))

    def test_the_provisioning_address_carries_the_secret_and_the_name(self):
        uri = provisioning_uri("ABCDEF", "me@example.com", "Auth Tutorial")
        self.assertTrue(uri.startswith("otpauth://totp/"))
        self.assertIn("secret=ABCDEF", uri)
        self.assertIn("issuer=Auth%20Tutorial", uri)


class TwoFactorTestCase(TestCase):
    """One person (not yet using two-factor), one who never will, and a fixed clock."""

    def setUp(self):
        make_user()
        make_user("plain@example.com")
        self.step = START
        patcher = mock.patch("accounts.totp.current_step", side_effect=lambda now=None: self.step)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.laptop = login(self.client).json()

    def tick(self, steps=1):
        self.step += steps

    def code(self, offset=0, secret=None):
        return code_for(secret or self.secret, self.step + offset)

    def start_setup(self):
        self.secret = setup(self.client, self.laptop["access_token"]).json()["secret"]
        return self.secret

    def enable(self):
        """Switch two-factor on, then let the clock move on, as the person's next login would."""
        self.start_setup()
        self.recovery = confirm(self.client, self.laptop["access_token"], self.code()).json()["recovery_codes"]
        self.tick()

    def password_step(self, **extra):
        return login(self.client, **extra).json()["mfa_token"]


class EnrolHappyPathTests(TwoFactorTestCase):
    def test_setup_gives_a_secret_and_an_address_for_the_app(self):         # start_setup
        resp = setup(self.client, self.laptop["access_token"])
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(len(body["secret"]), 32)
        self.assertIn(body["secret"], body["otpauth_uri"])

    def test_setup_alone_does_not_switch_it_on(self):                       # start_setup
        self.start_setup()
        self.assertIsNone(TotpDevice.objects.get().confirmed_at)
        self.assertEqual(login(self.client).status_code, 200)
        self.assertIn("access_token", login(self.client).json())            # still just a password

    def test_asking_again_before_confirming_replaces_the_secret(self):      # start_setup
        first = self.start_setup()
        second = self.start_setup()
        self.assertNotEqual(first, second)
        self.assertEqual(TotpDevice.objects.count(), 1)
        self.assertEqual(confirm(self.client, self.laptop["access_token"], code_for(first, self.step)).status_code, 400)
        self.assertEqual(confirm(self.client, self.laptop["access_token"], code_for(second, self.step)).status_code, 200)

    def test_confirming_with_the_right_code_switches_it_on(self):           # switch_on
        self.start_setup()
        resp = confirm(self.client, self.laptop["access_token"], self.code())
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(TotpDevice.objects.get().confirmed_at)

    def test_confirming_gives_eight_recovery_codes(self):                   # issue_recovery_codes
        self.start_setup()
        codes = confirm(self.client, self.laptop["access_token"], self.code()).json()["recovery_codes"]
        self.assertEqual(len(codes), 8)
        self.assertEqual(len(set(codes)), 8)
        for c in codes:
            self.assertRegex(c, r"^[0-9a-f]{5}-[0-9a-f]{5}$")

    def test_only_hashes_of_the_recovery_codes_are_stored(self):            # issue_recovery_codes
        self.start_setup()
        codes = confirm(self.client, self.laptop["access_token"], self.code()).json()["recovery_codes"]
        stored = set(RecoveryCode.objects.values_list("code_hash", flat=True))
        self.assertEqual(stored, {hash_secret(c.replace("-", "")) for c in codes})
        for c in codes:
            self.assertNotIn(c.replace("-", ""), stored)

    def test_afterwards_the_password_alone_no_longer_logs_in(self):         # switch_on
        self.enable()
        body = login(self.client).json()
        self.assertTrue(body["mfa_required"])
        self.assertNotIn("access_token", body)


class EnrolUnhappyPathTests(TwoFactorTestCase):
    def test_setup_needs_a_login(self):
        self.assertEqual(self.client.post(SETUP, data="{}", content_type="application/json").status_code, 401)
        self.assertEqual(setup(self.client, "not-a-token").status_code, 401)

    def test_confirm_needs_a_login(self):
        resp = self.client.post(CONFIRM, data=json.dumps({"code": "123456"}), content_type="application/json")
        self.assertEqual(resp.status_code, 401)

    def test_setup_when_it_is_already_on_is_refused(self):                  # start_setup
        self.enable()
        resp = setup(self.client, self.laptop["access_token"])
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(TotpDevice.objects.count(), 1)

    def test_a_wrong_code_does_not_switch_it_on(self):                      # check_setup_code
        self.start_setup()
        resp = confirm(self.client, self.laptop["access_token"], "000000" if self.code() != "000000" else "111111")
        self.assertEqual(resp.status_code, 400)
        self.assertIsNone(TotpDevice.objects.get().confirmed_at)
        self.assertEqual(RecoveryCode.objects.count(), 0)
        self.assertIn("access_token", login(self.client).json())            # the person is not locked out

    def test_confirming_without_starting_setup_is_refused(self):            # find_pending_device
        resp = confirm(self.client, self.laptop["access_token"], "123456")
        self.assertEqual(resp.status_code, 400)

    def test_confirming_when_it_is_already_on_is_refused(self):             # find_pending_device
        self.enable()
        self.assertEqual(confirm(self.client, self.laptop["access_token"], self.code()).status_code, 409)

    def test_missing_code(self):
        self.start_setup()
        resp = self.client.post(CONFIRM, data="{}", content_type="application/json", **bearer(self.laptop["access_token"]))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("code", resp.json()["errors"])

    def test_body_that_is_not_json(self):
        resp = self.client.post(CONFIRM, data="nope", content_type="application/json", **bearer(self.laptop["access_token"]))
        self.assertEqual(resp.status_code, 400)

    def test_only_post_is_allowed(self):
        self.assertEqual(self.client.get(SETUP).status_code, 405)
        self.assertEqual(self.client.get(CONFIRM).status_code, 405)
        self.assertEqual(self.client.get(CODE_LOGIN).status_code, 405)


class SecondStepHappyPathTests(TwoFactorTestCase):
    def setUp(self):
        super().setUp()
        self.enable()

    def test_the_password_step_hands_back_a_note_not_tokens(self):          # start_second_step
        resp = login(self.client)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(set(body), {"mfa_required", "mfa_token", "expires_in"})
        self.assertEqual(body["expires_in"], 300)

    def test_the_password_step_makes_no_login(self):                        # start_second_step
        before = RefreshToken.objects.count()
        login(self.client)
        self.assertEqual(RefreshToken.objects.count(), before)

    def test_the_right_code_gives_the_tokens(self):                         # issue_tokens
        resp = code_login(self.client, self.password_step(), self.code())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(set(resp.json()), {"access_token", "refresh_token", "expires_in"})

    def test_those_tokens_work(self):
        tokens = code_login(self.client, self.password_step(), self.code()).json()
        resp = self.client.get(ME, **bearer(tokens["access_token"]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"email": EMAIL, "role": "member"})

    def test_the_code_from_the_step_before_is_accepted(self):               # use_totp_code (clock drift)
        self.tick(2)
        resp = code_login(self.client, self.password_step(), self.code(offset=-1))
        self.assertEqual(resp.status_code, 200)

    def test_a_recovery_code_works(self):                                   # use_recovery_code
        resp = code_login(self.client, self.password_step(), self.recovery[0])
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access_token", resp.json())

    def test_a_recovery_code_is_forgiving_about_dashes_capitals_and_spaces(self):   # use_recovery_code
        messy = " " + self.recovery[1].replace("-", " ").upper() + " "
        self.assertEqual(code_login(self.client, self.password_step(), messy).status_code, 200)

    def test_a_recovery_code_works_once(self):                              # use_recovery_code
        self.assertEqual(code_login(self.client, self.password_step(), self.recovery[2]).status_code, 200)
        self.assertEqual(code_login(self.client, self.password_step(), self.recovery[2]).status_code, 401)

    def test_using_a_recovery_code_leaves_the_others_alone(self):           # use_recovery_code
        code_login(self.client, self.password_step(), self.recovery[3])
        self.assertEqual(code_login(self.client, self.password_step(), self.recovery[4]).status_code, 200)

    def test_a_person_without_two_factor_is_not_asked_for_a_code(self):     # check_second_step
        body = login(self.client, email="plain@example.com").json()
        self.assertIn("access_token", body)
        self.assertNotIn("mfa_required", body)

    def test_a_good_code_wipes_the_failure_count(self):                     # reset_failures
        for _ in range(3):
            code_login(self.client, self.password_step(), "not-a-code")
        self.assertEqual(LoginLock.objects.get(email=EMAIL).failed_count, 3)
        code_login(self.client, self.password_step(), self.code())
        self.assertEqual(LoginLock.objects.get(email=EMAIL).failed_count, 0)


class SecondStepUnhappyPathTests(TwoFactorTestCase):
    def setUp(self):
        super().setUp()
        self.enable()

    def wrong_code(self):
        right = self.code()
        return "000000" if right != "000000" else "111111"

    def test_a_wrong_code_is_refused_and_gives_no_tokens(self):             # check_second_factor
        resp = code_login(self.client, self.password_step(), self.wrong_code())
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json(), {"detail": "That code is not right."})
        self.assertEqual(RefreshToken.objects.filter(user__username=EMAIL).count(), 1)   # only the setup login's

    def test_a_code_works_once(self):                                       # use_totp_code
        code = self.code()
        self.assertEqual(code_login(self.client, self.password_step(), code).status_code, 200)
        resp = code_login(self.client, self.password_step(), code)
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json(), {"detail": "That code is not right."})   # same words as any wrong code

    def test_an_earlier_code_is_refused_after_a_later_one_was_used(self):   # use_totp_code
        self.tick()
        earlier = self.code(offset=-1)
        self.assertEqual(code_login(self.client, self.password_step(), self.code()).status_code, 200)
        self.assertEqual(code_login(self.client, self.password_step(), earlier).status_code, 401)

    def test_the_code_from_the_setup_step_cannot_be_used_to_log_in(self):   # switch_on
        # enable() confirmed with the code of step START and moved the clock on one step.
        stale = code_for(self.secret, START)
        self.assertEqual(code_login(self.client, self.password_step(), stale).status_code, 401)

    def test_a_code_two_steps_away_is_refused(self):                        # use_totp_code
        for offset in (-2, 2):
            self.tick(5)
            resp = code_login(self.client, self.password_step(), self.code(offset=offset))
            self.assertEqual(resp.status_code, 401)

    def test_a_made_up_recovery_code_is_refused(self):                      # use_recovery_code
        self.assertEqual(code_login(self.client, self.password_step(), "aaaaa-bbbbb").status_code, 401)

    def test_a_forged_note_is_refused(self):                                # read_mfa_token
        resp = code_login(self.client, "not-a-real-note", self.code())
        self.assertEqual(resp.status_code, 401)

    def test_an_expired_note_is_refused(self):                              # read_mfa_token
        note = self.password_step()
        with override_settings(MFA_TOKEN_SECONDS=-1):
            resp = code_login(self.client, note, self.code())
        self.assertEqual(resp.status_code, 401)
        self.assertIn("too long", resp.json()["detail"])

    def test_an_access_token_is_not_accepted_as_the_note(self):             # read_mfa_token
        resp = code_login(self.client, self.laptop["access_token"], self.code())
        self.assertEqual(resp.status_code, 401)

    def test_the_note_is_not_a_login(self):                                 # start_second_step
        resp = self.client.get(ME, **bearer(self.password_step()))
        self.assertEqual(resp.status_code, 401)

    def test_a_note_for_an_account_since_deactivated_is_refused(self):      # read_mfa_token
        note = self.password_step()
        User.objects.filter(username=EMAIL).update(is_active=False)
        self.assertEqual(code_login(self.client, note, self.code()).status_code, 401)

    def test_five_wrong_codes_lock_the_address(self):                       # check_not_locked, record_failure
        note = self.password_step()
        for _ in range(5):
            code_login(self.client, note, self.wrong_code())
        resp = code_login(self.client, note, self.code())                   # even the RIGHT code
        self.assertEqual(resp.status_code, 429)

    def test_a_locked_address_cannot_get_past_the_password_step_either(self):    # check_not_locked
        note = self.password_step()
        for _ in range(5):
            code_login(self.client, note, self.wrong_code())
        self.assertEqual(login(self.client).status_code, 429)

    def test_logging_in_again_with_the_password_does_not_reset_the_count(self):  # check_second_step (the planted bug)
        for _ in range(5):
            code_login(self.client, self.password_step(), self.wrong_code())    # a fresh password step each time
        self.assertEqual(login(self.client).status_code, 429)

    def test_missing_fields(self):
        resp = self.client.post(CODE_LOGIN, data="{}", content_type="application/json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(set(resp.json()["errors"]), {"mfa_token", "code"})

    def test_body_that_is_not_json(self):
        self.assertEqual(self.client.post(CODE_LOGIN, data="nope", content_type="application/json").status_code, 400)


# Django's test runner switches DEBUG off, and the development tracing rule
# only works while DEBUG is on, so these tests turn it back on.
@override_settings(DEBUG=True)
class TracingTests(TwoFactorTestCase):
    def labels(self):
        return list(RuntimeEvent.objects.filter(event_type="checkpoint").order_by("seq").values_list("label", flat=True))

    def calls(self):
        return set(RuntimeEvent.objects.filter(event_type="call").values_list("qualname", flat=True))

    def test_setup_shows_the_steps_and_decisions(self):
        setup(self.client, self.laptop["access_token"], HTTP_X_TRACKER="1")
        self.assertEqual(self.calls(), {"two_factor_setup_view", "authenticate_access", "start_setup"})
        self.assertEqual(self.labels(), ["access_check", "device_lookup", "setup_started"])

    def test_confirming_shows_every_step(self):
        self.start_setup()
        confirm(self.client, self.laptop["access_token"], self.code(), HTTP_X_TRACKER="1")
        self.assertEqual(self.calls(), {
            "two_factor_confirm_view", "authenticate_access", "confirm_two_factor", "find_pending_device",
            "check_setup_code", "switch_on", "issue_recovery_codes"})
        self.assertEqual(self.labels(), [
            "access_check", "pending_lookup", "code_check", "two_factor_on", "recovery_issued"])

    def test_the_password_step_stops_before_wiping_the_failure_count(self):
        self.enable()
        login(self.client, HTTP_X_TRACKER="1")
        self.assertEqual(self.labels(), [
            "lock_check", "credentials_check", "active_check", "second_step_check", "second_step_started"])
        self.assertNotIn("failures_reset", self.labels())       # the planted bug adds it back here

    def test_the_code_step_shows_every_step(self):
        self.enable()
        note = self.password_step()
        RuntimeEvent.objects.all().delete()
        code_login(self.client, note, self.code(), HTTP_X_TRACKER="1")
        self.assertEqual(self.calls(), {
            "two_factor_login_view", "complete_login", "read_mfa_token", "check_not_locked",
            "check_second_factor", "use_totp_code", "reset_failures", "issue_tokens"})
        self.assertEqual(self.labels(), [
            "mfa_token_check", "lock_check", "totp_check", "failures_reset", "tokens_issued"])

    def test_a_wrong_code_stops_at_the_failure(self):
        self.enable()
        note = self.password_step()
        code_login(self.client, note, "000000" if self.code() != "000000" else "111111", HTTP_X_TRACKER="1")
        self.assertEqual(self.labels(), ["mfa_token_check", "lock_check", "totp_check", "failure_recorded"])

    def totp_values(self):
        event = RuntimeEvent.objects.filter(label="totp_check").order_by("seq").last()
        values = event.values_json if isinstance(event.values_json, dict) else json.loads(event.values_json)
        return {k: str(v) for k, v in values.items()}

    def test_a_wrong_code_and_a_replayed_code_look_different_in_the_trace(self):
        self.enable()
        good = self.code()
        code_login(self.client, self.password_step(), good)                 # uses the step up
        RuntimeEvent.objects.all().delete()
        code_login(self.client, self.password_step(), good, HTTP_X_TRACKER="1")      # the SAME code again
        self.assertEqual(self.totp_values(), {"has_device": "True", "matched": "True", "replayed": "True", "claimed": "0"})
        RuntimeEvent.objects.all().delete()
        code_login(self.client, self.password_step(), "000000" if self.code(1) != "000000" else "111111", HTTP_X_TRACKER="1")
        self.assertEqual(self.totp_values(), {"has_device": "True", "matched": "False", "replayed": "False", "claimed": "0"})
        RuntimeEvent.objects.all().delete()
        self.tick()
        code_login(self.client, self.password_step(), self.code(), HTTP_X_TRACKER="1")   # a fresh code
        self.assertEqual(self.totp_values(), {"has_device": "True", "matched": "True", "replayed": "False", "claimed": "1"})

    def test_a_recovery_code_shows_how_many_are_left(self):
        self.enable()
        note = self.password_step()
        code_login(self.client, note, self.recovery[0], HTTP_X_TRACKER="1")
        event = RuntimeEvent.objects.get(label="recovery_check")
        values = event.values_json if isinstance(event.values_json, dict) else json.loads(event.values_json)
        self.assertEqual(str(values["codes_left"]), "7")

    def test_redaction_audit_no_secret_is_stored(self):
        self.start_setup()
        first_secret = self.secret
        resp = setup(self.client, self.laptop["access_token"], HTTP_X_TRACKER="1")
        self.secret = resp.json()["secret"]
        uri = resp.json()["otpauth_uri"]
        good = self.code()
        recovery = confirm(self.client, self.laptop["access_token"], good, HTTP_X_TRACKER="1").json()["recovery_codes"]
        self.tick()
        note = login(self.client, HTTP_X_TRACKER="1").json()["mfa_token"]
        next_code = self.code()
        tokens = code_login(self.client, note, next_code, HTTP_X_TRACKER="1").json()
        code_login(self.client, note, recovery[0], HTTP_X_TRACKER="1")
        self.assertGreaterEqual(TraceRun.objects.count(), 5)
        self.assertGreater(RuntimeEvent.objects.count(), 0)         # an empty trace would pass vacuously
        stored = json.dumps(
            list(RuntimeEvent.objects.values(
                "qualname", "label", "args_json", "return_repr", "exception_repr", "values_json"))
            + list(TraceRun.objects.values("path", "method")),
            default=str,
        )
        secrets_to_hide = [self.secret, first_secret, uri, good, next_code, note, EMAIL, GOOD_PASSWORD,
                           tokens["access_token"], tokens["refresh_token"], self.laptop["access_token"],
                           self.laptop["refresh_token"], *recovery, *[c.replace("-", "") for c in recovery]]
        for secret in secrets_to_hide:
            self.assertNotIn(secret, stored, f"{secret!r} leaked into the stored trace")
