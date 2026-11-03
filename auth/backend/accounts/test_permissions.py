"""
Episode 8 tests. Each name says which step of the Permissions flows it protects.

Run:  python manage.py test accounts.test_permissions -v 2

Three people are made for every test:  an admin, a member, and a second member.
"""
import json

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from tracker.models import RuntimeEvent, TraceRun

from .login import ACCESS_SALT
from .models import AccountRole, LoginLock, RefreshToken, TotpDevice
from .test_login import ME, login, make_user
from .tests import GOOD_PASSWORD

User = get_user_model()

USERS = "/api/auth/admin/users/"
ROLE = "/api/auth/admin/role/"
BOSS = "boss@example.com"
MEMBER = "member@example.com"
OTHER = "other@example.com"
NOT_ALLOWED = "You do not have permission to do that."


def bearer(access_token):
    return {"HTTP_AUTHORIZATION": f"Bearer {access_token}"}


def set_role(client, access_token, user_id, role, **extra):
    return client.post(ROLE, data=json.dumps({"user_id": user_id, "role": role}),
                       content_type="application/json", **bearer(access_token), **extra)


class PermissionTestCase(TestCase):
    def setUp(self):
        self.boss = make_user(BOSS)
        self.member = make_user(MEMBER)
        self.other = make_user(OTHER)
        AccountRole.objects.create(user=self.boss, role="admin")

    def token(self, email):
        return login(self.client, email=email).json()["access_token"]

    def role_in_db(self, user):
        row = AccountRole.objects.filter(user=user).first()
        return row.role if row else "member"


class HappyPathTests(PermissionTestCase):
    def test_a_new_account_is_a_member_by_default(self):                      # check_role
        self.assertFalse(AccountRole.objects.filter(user=self.member).exists())
        resp = self.client.get(ME, **bearer(self.token(MEMBER)))
        self.assertEqual(resp.json(), {"email": MEMBER, "role": "member"})

    def test_me_shows_an_admin_as_an_admin(self):
        resp = self.client.get(ME, **bearer(self.token(BOSS)))
        self.assertEqual(resp.json(), {"email": BOSS, "role": "admin"})

    def test_an_admin_sees_every_account_with_its_role(self):                 # list_users
        resp = self.client.get(USERS, **bearer(self.token(BOSS)))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["users"], [
            {"id": self.boss.pk, "email": BOSS, "role": "admin", "active": True},
            {"id": self.member.pk, "email": MEMBER, "role": "member", "active": True},
            {"id": self.other.pk, "email": OTHER, "role": "member", "active": True},
        ])

    def test_an_admin_can_make_a_member_an_admin(self):                       # apply_role
        resp = set_role(self.client, self.token(BOSS), self.member.pk, "admin")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"detail": "Role changed.", "id": self.member.pk, "role": "admin"})
        self.assertEqual(self.role_in_db(self.member), "admin")

    def test_an_admin_can_make_another_admin_a_member_again(self):
        AccountRole.objects.create(user=self.member, role="admin")
        resp = set_role(self.client, self.token(BOSS), self.member.pk, "member")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.role_in_db(self.member), "member")

    def test_setting_the_role_someone_already_has_is_harmless(self):
        resp = set_role(self.client, self.token(BOSS), self.member.pk, "member")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.role_in_db(self.member), "member")

    def test_the_access_token_carries_no_role(self):
        # The role is read from the database on every request. If it were copied
        # into the token, a demoted admin would stay an admin until the token expired.
        token = self.token(BOSS)
        self.assertEqual(signing.loads(token, salt=ACCESS_SALT), {"uid": self.boss.pk})

    def test_changing_a_role_does_not_log_the_person_out(self):
        self.token(MEMBER)
        set_role(self.client, self.token(BOSS), self.member.pk, "admin")
        self.assertFalse(RefreshToken.objects.filter(user=self.member, revoked_at__isnull=False).exists())


class UnhappyPathTests(PermissionTestCase):
    # --- who are you? (401) -------------------------------------------------
    def test_the_list_needs_a_login(self):
        resp = self.client.get(USERS)
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json(), {"detail": "Not logged in."})

    def test_the_list_refuses_a_damaged_token(self):
        resp = self.client.get(USERS, **bearer(self.token(BOSS) + "x"))
        self.assertEqual(resp.status_code, 401)

    def test_changing_a_role_needs_a_login(self):
        resp = self.client.post(ROLE, data=json.dumps({"user_id": self.member.pk, "role": "admin"}),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(self.role_in_db(self.member), "member")

    def test_an_admin_who_has_been_switched_off_is_not_logged_in(self):
        token = self.token(BOSS)
        self.boss.is_active = False
        self.boss.save(update_fields=["is_active"])
        self.assertEqual(self.client.get(USERS, **bearer(token)).status_code, 401)

    # --- are you allowed? (403) ---------------------------------------------
    def test_a_member_cannot_see_the_list(self):
        resp = self.client.get(USERS, **bearer(self.token(MEMBER)))
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json(), {"detail": NOT_ALLOWED})
        self.assertNotIn(OTHER, resp.content.decode())             # nothing about anyone else

    def test_a_member_cannot_change_someone_elses_role(self):
        resp = set_role(self.client, self.token(MEMBER), self.other.pk, "admin")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.role_in_db(self.other), "member")

    def test_a_member_cannot_make_themselves_an_admin(self):                 # the planted bug opens this
        resp = set_role(self.client, self.token(MEMBER), self.member.pk, "admin")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.role_in_db(self.member), "member")
        self.assertFalse(AccountRole.objects.filter(user=self.member).exists())

    def test_a_member_cannot_remove_an_admin(self):
        resp = set_role(self.client, self.token(MEMBER), self.boss.pk, "member")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.role_in_db(self.boss), "admin")

    def test_a_member_asking_about_a_missing_account_still_gets_403_not_404(self):
        # Otherwise the admin page could be used to find out which ids exist.
        resp = set_role(self.client, self.token(MEMBER), 99999, "admin")
        self.assertEqual(resp.status_code, 403)

    def test_a_member_sending_nonsense_still_gets_403(self):
        resp = set_role(self.client, self.token(MEMBER), "x", "wizard")
        self.assertEqual(resp.status_code, 403)

    # --- admins asking for something that makes no sense (400, 404, 409) ----
    def test_an_unknown_account_is_a_404(self):
        resp = set_role(self.client, self.token(BOSS), 99999, "admin")
        self.assertEqual(resp.status_code, 404)

    def test_an_unknown_role_is_refused_and_nothing_changes(self):
        resp = set_role(self.client, self.token(BOSS), self.member.pk, "wizard")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json(), {"detail": "The role must be one of: member, admin."})
        self.assertEqual(self.role_in_db(self.member), "member")

    def test_a_missing_role_is_refused(self):
        resp = self.client.post(ROLE, data=json.dumps({"user_id": self.member.pk}),
                                content_type="application/json", **bearer(self.token(BOSS)))
        self.assertEqual(resp.status_code, 400)

    def test_the_account_id_must_be_a_whole_number(self):
        token = self.token(BOSS)
        for bad in (str(self.member.pk), None, 1.5, True, [self.member.pk]):
            resp = set_role(self.client, token, bad, "admin")
            self.assertEqual(resp.status_code, 400, repr(bad))
        self.assertEqual(self.role_in_db(self.member), "member")

    def test_the_body_must_be_a_json_object(self):
        resp = self.client.post(ROLE, data="nope", content_type="application/json", **bearer(self.token(BOSS)))
        self.assertEqual(resp.status_code, 400)

    def test_the_last_admin_cannot_be_demoted_by_anyone(self):
        AccountRole.objects.create(user=self.member, role="admin")
        AccountRole.objects.filter(user=self.boss).delete()                  # member is now the only admin
        resp = set_role(self.client, self.token(MEMBER), self.member.pk, "member")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(self.role_in_db(self.member), "admin")

    def test_the_only_admin_cannot_demote_themselves(self):
        resp = set_role(self.client, self.token(BOSS), self.boss.pk, "member")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json(), {"detail": "That would leave no admin. Make someone else an admin first."})
        self.assertEqual(self.role_in_db(self.boss), "admin")

    def test_an_admin_can_step_down_once_someone_else_is_an_admin(self):
        AccountRole.objects.create(user=self.member, role="admin")
        resp = set_role(self.client, self.token(BOSS), self.boss.pk, "member")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.role_in_db(self.boss), "member")

    def test_the_wrong_method_is_refused(self):
        token = self.token(BOSS)
        self.assertEqual(self.client.post(USERS, data="{}", content_type="application/json", **bearer(token)).status_code, 405)
        self.assertEqual(self.client.get(ROLE, **bearer(token)).status_code, 405)

    # --- a role that changes while someone is logged in ---------------------
    def test_a_demoted_admin_loses_the_power_on_the_very_next_request(self):
        AccountRole.objects.create(user=self.member, role="admin")
        old_token = self.token(MEMBER)                                           # taken while an admin
        self.assertEqual(self.client.get(USERS, **bearer(old_token)).status_code, 200)
        set_role(self.client, self.token(BOSS), self.member.pk, "member")
        self.assertEqual(self.client.get(USERS, **bearer(old_token)).status_code, 403)   # same token, no power

    def test_a_promoted_member_gains_the_power_on_the_very_next_request(self):
        old_token = self.token(MEMBER)                                           # taken while a member
        self.assertEqual(self.client.get(USERS, **bearer(old_token)).status_code, 403)
        set_role(self.client, self.token(BOSS), self.member.pk, "admin")
        self.assertEqual(self.client.get(USERS, **bearer(old_token)).status_code, 200)


# Django's test runner switches DEBUG off, and the development tracing rule
# only works while DEBUG is on, so these tests turn it back on.
@override_settings(DEBUG=True)
class TracingTests(PermissionTestCase):
    def labels(self):
        return list(RuntimeEvent.objects.filter(event_type="checkpoint").order_by("seq").values_list("label", flat=True))

    def calls(self):
        return set(RuntimeEvent.objects.filter(event_type="call").values_list("qualname", flat=True))

    def values(self, label):
        event = RuntimeEvent.objects.filter(label=label).order_by("seq").last()
        values = event.values_json if isinstance(event.values_json, dict) else json.loads(event.values_json)
        return {k: str(v) for k, v in values.items()}

    def test_listing_shows_the_steps_and_decisions(self):
        token = self.token(BOSS)
        RuntimeEvent.objects.all().delete()
        self.client.get(USERS, HTTP_X_TRACKER="1", **bearer(token))
        self.assertEqual(self.calls(), {"admin_users_view", "authenticate_access", "list_users", "check_role"})
        self.assertEqual(self.labels(), ["access_check", "role_check", "users_listed"])
        self.assertEqual(self.values("role_check"), {"needed": "'admin'", "has": "'admin'", "allowed": "True"})

    def test_a_refused_member_stops_at_the_role_check(self):
        token = self.token(MEMBER)
        RuntimeEvent.objects.all().delete()
        self.client.get(USERS, HTTP_X_TRACKER="1", **bearer(token))
        self.assertEqual(self.labels(), ["access_check", "role_check"])          # nothing was listed
        self.assertEqual(self.values("role_check"), {"needed": "'admin'", "has": "'member'", "allowed": "False"})

    def test_changing_a_role_shows_every_step(self):
        token = self.token(BOSS)
        RuntimeEvent.objects.all().delete()
        set_role(self.client, token, self.member.pk, "admin", HTTP_X_TRACKER="1")
        self.assertEqual(self.calls(), {
            "admin_role_view", "authenticate_access", "change_role", "check_role", "check_role_input",
            "find_target", "check_not_last_admin", "apply_role"})
        self.assertEqual(self.labels(), [
            "access_check", "role_check", "role_input_check", "target_lookup", "last_admin_check", "role_changed"])

    def test_the_permission_is_checked_before_the_request_is_looked_at(self):
        token = self.token(MEMBER)
        RuntimeEvent.objects.all().delete()
        set_role(self.client, token, 99999, "wizard", HTTP_X_TRACKER="1")        # nonsense AND forbidden
        self.assertEqual(self.labels(), ["access_check", "role_check"])          # refused before any of it is read

    def test_the_last_admin_check_says_why_it_refused(self):
        token = self.token(BOSS)
        RuntimeEvent.objects.all().delete()
        set_role(self.client, token, self.boss.pk, "member", HTTP_X_TRACKER="1")
        self.assertEqual(self.labels()[-1], "last_admin_check")
        self.assertEqual(self.values("last_admin_check"), {"would_leave_none": "True"})

    def test_redaction_audit_no_address_is_stored(self):
        token = self.token(BOSS)
        RuntimeEvent.objects.all().delete()
        listed = self.client.get(USERS, HTTP_X_TRACKER="1", **bearer(token))
        self.assertEqual(listed.status_code, 200)
        self.assertGreater(RuntimeEvent.objects.count(), 0)         # an empty trace would pass vacuously
        stored = json.dumps(
            list(RuntimeEvent.objects.values(
                "qualname", "label", "args_json", "return_repr", "exception_repr", "values_json"))
            + list(TraceRun.objects.values("path", "method")),
            default=str,
        )
        for secret in (BOSS, MEMBER, OTHER, token):
            self.assertNotIn(secret, stored, f"{secret!r} leaked into the stored trace")


@override_settings(DEBUG=True)
class DemoCommandTests(TestCase):
    """The two development commands that set a walkthrough up (they never run on a real server)."""

    def seed(self):
        from io import StringIO
        call_command("seed_demo", stdout=StringIO())

    def test_seed_demo_makes_an_admin_and_two_members_who_can_log_in(self):
        self.seed()
        roles = {a.user.username: a.role for a in AccountRole.objects.select_related("user")}
        self.assertEqual(roles, {"admin@example.com": "admin", "member@example.com": "member",
                                 "member2@example.com": "member"})
        resp = login(self.client, email="admin@example.com", password="demo-password-55")
        self.assertEqual(resp.status_code, 200)

    def test_seed_demo_can_be_run_again_to_put_things_back(self):
        self.seed()
        admin = User.objects.get(username="admin@example.com")
        AccountRole.objects.filter(user=admin).update(role="member")
        TotpDevice.objects.create(user=admin, secret="X" * 32)
        LoginLock.objects.create(email="admin@example.com", failed_count=3)
        self.seed()
        self.assertEqual(AccountRole.objects.get(user=admin).role, "admin")
        self.assertFalse(TotpDevice.objects.filter(user=admin).exists())
        self.assertFalse(LoginLock.objects.filter(email="admin@example.com").exists())
        self.assertEqual(User.objects.filter(username__endswith="@example.com").count(), 3)

    def test_seed_demo_leaves_other_accounts_alone(self):
        other = make_user("someone.else@example.com")
        self.seed()
        other.refresh_from_db()
        self.assertTrue(other.check_password(GOOD_PASSWORD))

    @override_settings(DEBUG=False)
    def test_seed_demo_refuses_to_run_on_a_real_server(self):
        with self.assertRaises(CommandError):
            self.seed()
        self.assertFalse(User.objects.filter(username="admin@example.com").exists())

    def test_make_admin_makes_the_first_admin(self):
        from io import StringIO
        make_user("first@example.com")
        call_command("make_admin", email="first@example.com", stdout=StringIO())
        self.assertEqual(AccountRole.objects.get(user__username="first@example.com").role, "admin")
        call_command("make_admin", email="first@example.com", member=True, stdout=StringIO())
        self.assertEqual(AccountRole.objects.get(user__username="first@example.com").role, "member")

    def test_make_admin_refuses_an_address_with_no_account(self):
        with self.assertRaises(CommandError):
            call_command("make_admin", email="nobody@example.com")
