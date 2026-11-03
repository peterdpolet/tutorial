"""
Episode 8: who may do what.

Logging in answers "who are you?". This file answers a different question:
"are you allowed to do THIS?". The two are separate on purpose, and the most
common hole in real systems is a page that asks the first question and forgets
the second.

Two roles, ordered:

  member   the default. Every account is one until someone makes it an admin.
  admin    can see the list of accounts and change anyone's role.

The rule lives in ONE place, `check_role`, and every protected action calls it
as its first step. That is what makes it testable: one rule, one trace line
(`role_check`), one reason a request was refused.

Two decisions worth knowing before you read the code:

  * The role is looked up from the database on every request (see AccountRole).
    A demoted admin loses their power on their next request, not 15 minutes later.
  * The permission is checked BEFORE the request is looked at. A member who asks
    to change the role of an account that does not exist gets "no permission",
    not "no such account", so they cannot use the admin page to find out which
    accounts exist.
"""
from django.contrib.auth import get_user_model
from django.db import transaction

from tracker.tracker import checkpoint, traced

from .login import LoginError
from .models import AccountRole

User = get_user_model()

ROLE_MEMBER = "member"
ROLE_ADMIN = "admin"
ROLES = (ROLE_MEMBER, ROLE_ADMIN)          # lowest first: a later role can do what an earlier one can
NOT_ALLOWED = "You do not have permission to do that."


class AccessError(LoginError):
    """A refusal with its own status: 403 not allowed, 404 no such account, 409 not safe."""


def role_of(*, user):
    """The role a person has right now. Not traced: it is a plain lookup used by several steps."""
    row = AccountRole.objects.filter(user=user).first()
    return row.role if row else ROLE_MEMBER


@traced("check_role")
def check_role(*, user, needed):
    has = role_of(user=user)
    allowed = ROLES.index(has) >= ROLES.index(needed)
    checkpoint("role_check", needed=needed, has=has, allowed=allowed)
    if not allowed:
        raise AccessError(403, NOT_ALLOWED)


# ---- A. see the list of accounts -------------------------------------------

@traced("list_users")
def list_users(*, actor):
    check_role(user=actor, needed=ROLE_ADMIN)
    people = []
    for user in User.objects.order_by("pk"):
        people.append({"id": user.pk, "email": user.username, "role": role_of(user=user), "active": user.is_active})
    checkpoint("users_listed", count=len(people))
    # Returned under a NAME so the tracker can hide the addresses (see episode 7).
    return {"users": people}


# ---- B. change someone's role ----------------------------------------------

@traced("check_role_input")
def check_role_input(*, user_id, role):
    ok_id = isinstance(user_id, int) and not isinstance(user_id, bool)
    ok_role = role in ROLES
    checkpoint("role_input_check", id_ok=ok_id, role_ok=ok_role)
    if not ok_id:
        raise AccessError(400, "Say which account, by its id.")
    if not ok_role:
        raise AccessError(400, "The role must be one of: " + ", ".join(ROLES) + ".")


@traced("find_target")
def find_target(*, user_id):
    target = User.objects.filter(pk=user_id).first()
    checkpoint("target_lookup", found=target is not None)
    if target is None:
        raise AccessError(404, "There is no account with that id.")
    return target


@traced("check_not_last_admin")
def check_not_last_admin(*, target, role):
    """Refuse a change that would leave the site with no admin at all."""
    would_leave_none = (
        role != ROLE_ADMIN
        and role_of(user=target) == ROLE_ADMIN
        and AccountRole.objects.filter(role=ROLE_ADMIN).exclude(user=target).count() == 0
    )
    checkpoint("last_admin_check", would_leave_none=would_leave_none)
    if would_leave_none:
        raise AccessError(409, "That would leave no admin. Make someone else an admin first.")


@traced("apply_role")
def apply_role(*, target, role):
    with transaction.atomic():
        AccountRole.objects.update_or_create(user=target, defaults={"role": role})
    checkpoint("role_changed", user_id=target.pk, role=role)
    return {"detail": "Role changed.", "id": target.pk, "role": role}


@traced("change_role")
def change_role(*, actor, user_id, role):
    check_role(user=actor, needed=ROLE_ADMIN)            # 1 may this person do this at all?
    check_role_input(user_id=user_id, role=role)         # 2 only then: is the request sensible?
    target = find_target(user_id=user_id)                # 3 does the account exist?
    check_not_last_admin(target=target, role=role)       # 4 would it lock everyone out?
    return apply_role(target=target, role=role)          # 5 do it
