"""
Episode 3: Login.

The person types an email and password. The server decides whether they are
who they say, and if so hands back two tokens.

    login_view (views.py)             reads the request, shapes the reply
      -> login                        the one entry point; runs the steps below
           1. normalise_email         tidy the address (same rule as Register)
           2. check_not_locked        too many recent failures? stop here
           3. check_credentials       user exists AND password matches
                                      (on a miss: record_failure)
           4. check_active            correct password, but email never confirmed?
           5. reset_failures          a good login wipes the failure count
           6. issue_tokens            make the access token and refresh token

    me_view (views.py)                proves the access token works
      -> authenticate_access          read the token, find the user

Two deliberate choices, both visible in the trace:

  * A wrong password and an unknown email give the SAME reply. Otherwise the
    login form tells a stranger which addresses have accounts.
  * Failures are counted per address typed, not per account, so an address
    with no account locks the same way and leaks nothing.

The numbers (5 failures, 15 minutes, 15-minute access token, 14-day refresh
token) are invented for the tutorial; they live in settings.py.
"""
import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password as hash_matches, make_password
from django.core import signing
from django.db import transaction
from django.utils import timezone

from tracker.tracker import checkpoint, traced

from .models import LoginLock, RefreshToken

User = get_user_model()

ACCESS_SALT = "auth-tutorial.access"
BAD_LOGIN = "Email or password is incorrect."

# A real hash of a throw-away string. When the email is unknown we still check
# the password against this, so "no such user" is not noticeably faster than
# "wrong password".
_DUMMY_HASH = make_password("not-a-real-password")


class LoginError(Exception):
    """A refusal. `status` is the HTTP status, `detail` the sentence for the person."""

    def __init__(self, status, detail):
        super().__init__(detail)
        self.status = status
        self.detail = detail


@traced("normalise_email")
def normalise_email(*, email):
    return (email or "").strip().lower()


@traced("check_not_locked")
def check_not_locked(*, email):
    row = LoginLock.objects.filter(email=email).first()
    now = timezone.now()
    locked = bool(row and row.locked_until and row.locked_until > now)
    checkpoint("lock_check", locked=locked, failures=row.failed_count if row else 0)
    if locked:
        minutes = max(1, int((row.locked_until - now).total_seconds() // 60) + 1)
        raise LoginError(429, f"Too many failed attempts. Try again in {minutes} minute(s).")


@traced("record_failure")
def record_failure(*, email):
    with transaction.atomic():
        row, _ = LoginLock.objects.select_for_update().get_or_create(email=email)
        row.failed_count += 1
        failures = row.failed_count          # the count that decided it, before any reset below
        locked = failures >= settings.LOGIN_MAX_FAILURES
        if locked:
            row.locked_until = timezone.now() + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
            row.failed_count = 0
        row.save()
    checkpoint("failure_recorded", failures=failures, max_failures=settings.LOGIN_MAX_FAILURES, locked=locked)


@traced("check_credentials")
def check_credentials(*, email, password):
    user = User.objects.filter(username=email).first()
    # Always do one password check, even when there is no such user.
    password_ok = hash_matches(password, user.password if user else _DUMMY_HASH)
    ok = user is not None and password_ok
    checkpoint("credentials_check", user_found=user is not None, password_ok=password_ok)
    if not ok:
        record_failure(email=email)
        raise LoginError(401, BAD_LOGIN)
    return user


@traced("check_active")
def check_active(*, user):
    checkpoint("active_check", active=user.is_active)
    if not user.is_active:
        raise LoginError(403, "Confirm your email address first: use the link we emailed you.")


@traced("reset_failures")
def reset_failures(*, email):
    LoginLock.objects.filter(email=email).update(failed_count=0, locked_until=None)
    checkpoint("failures_reset")


@traced("issue_tokens")
def issue_tokens(*, user):
    access_token = signing.dumps({"uid": user.pk}, salt=ACCESS_SALT)
    refresh_token = secrets.token_urlsafe(32)
    RefreshToken.objects.create(
        user=user,
        token_hash=hashlib.sha256(refresh_token.encode()).hexdigest(),
        expires_at=timezone.now() + timedelta(days=settings.REFRESH_TOKEN_DAYS),
    )
    checkpoint(
        "tokens_issued",
        access_valid_seconds=settings.ACCESS_TOKEN_SECONDS,
        refresh_valid_days=settings.REFRESH_TOKEN_DAYS,
    )
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": settings.ACCESS_TOKEN_SECONDS,
    }


@traced("login")
def login(*, email, password):
    email = normalise_email(email=email)
    check_not_locked(email=email)
    user = check_credentials(email=email, password=password)
    check_active(user=user)
    reset_failures(email=email)
    return issue_tokens(user=user)


@traced("authenticate_access")
def authenticate_access(*, access_token):
    try:
        data = signing.loads(access_token, salt=ACCESS_SALT, max_age=settings.ACCESS_TOKEN_SECONDS)
    except signing.SignatureExpired:
        checkpoint("access_check", valid=False, why="expired")
        raise LoginError(401, "Your session has expired. Log in again.")
    except signing.BadSignature:
        checkpoint("access_check", valid=False, why="bad_signature")
        raise LoginError(401, "Not logged in.")
    user = User.objects.filter(pk=data.get("uid"), is_active=True).first()
    checkpoint("access_check", valid=user is not None, why="ok" if user else "no_such_user")
    if user is None:
        raise LoginError(401, "Not logged in.")
    return user
