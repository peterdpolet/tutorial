"""
Episode 4: Token refresh.

The access token only lasts 15 minutes. When it runs out, the page does not
ask for the password again: it hands over the refresh token and gets a fresh
pair. The old refresh token is retired at the same moment ("rotation").

    refresh_view (views.py)           reads the request, shapes the reply
      -> refresh                      the one entry point; runs the steps below
           1. find_refresh_token      the token must be one we issued
           2. check_not_replayed      a retired token coming back means theft
                                      (on a hit: revoke_family)
           3. check_refresh_not_expired  14 days (REFRESH_TOKEN_DAYS)
           4. check_user_active       the account must still be switched on
           5. rotate_tokens           retire this token, issue the next pair

Why rotate? A refresh token is the most valuable secret in the system: it makes
new access tokens for two weeks. If a thief copies one, rotation turns the
thief's copy into a trap. Whoever uses a token second (thief or owner) presents
a RETIRED token, and we answer by ending the whole login (the "family").
Both sides are then logged out; the owner logs in again, the thief cannot.

Same rules as the earlier episodes: every step is @traced, sits at module level
and takes keyword-only arguments, and records a checkpoint at each decision.
"""
from django.conf import settings
from django.utils import timezone

from tracker.tracker import checkpoint, traced

from .login import LoginError
from .models import RefreshToken
from .tokens import hash_refresh_token, make_access_token, store_refresh_token

ENDED = "This session has ended. Log in again."


@traced("find_refresh_token")
def find_refresh_token(*, refresh_token):
    row = (
        RefreshToken.objects.select_related("user")
        .filter(token_hash=hash_refresh_token(refresh_token))
        .first()
    )
    checkpoint("refresh_lookup", found=row is not None)
    if row is None:
        raise LoginError(401, "Not logged in.")
    return row


@traced("revoke_family")
def revoke_family(*, row):
    revoked = RefreshToken.objects.filter(family=row.family, revoked_at__isnull=True).update(
        revoked_at=timezone.now()
    )
    checkpoint("family_revoked", revoked_rows=revoked)


@traced("check_not_replayed")
def check_not_replayed(*, row):
    replayed = row.revoked_at is not None
    checkpoint("replay_check", replayed=replayed)
    if replayed:
        revoke_family(row=row)
        raise LoginError(401, ENDED)


@traced("check_refresh_not_expired")
def check_refresh_not_expired(*, row):
    now = timezone.now()
    expired = row.expires_at <= now
    checkpoint(
        "refresh_expiry_check",
        days_left=round((row.expires_at - now).total_seconds() / 86400, 2),
        expired=expired,
    )
    if expired:
        raise LoginError(401, "Your session has expired. Log in again.")


@traced("check_user_active")
def check_user_active(*, row):
    active = row.user.is_active
    checkpoint("user_active_check", active=active)
    if not active:
        raise LoginError(401, "Not logged in.")


@traced("rotate_tokens")
def rotate_tokens(*, row):
    # Retire this token with ONE database update that only succeeds if nobody
    # else has retired it first. Two requests carrying the same token cannot
    # both win (the same trick as episode 2's "claim the link").
    claimed = RefreshToken.objects.filter(pk=row.pk, revoked_at__isnull=True).update(
        revoked_at=timezone.now()
    )
    checkpoint("token_claimed", claimed=claimed)
    if claimed != 1:
        revoke_family(row=row)
        raise LoginError(401, ENDED)

    access_token = make_access_token(row.user)
    refresh_token = store_refresh_token(row.user, row.family)   # same login, next token
    checkpoint("tokens_rotated", access_valid_seconds=settings.ACCESS_TOKEN_SECONDS)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": settings.ACCESS_TOKEN_SECONDS,
    }


@traced("refresh")
def refresh(*, refresh_token):
    row = find_refresh_token(refresh_token=refresh_token)
    check_not_replayed(row=row)
    check_refresh_not_expired(row=row)
    check_user_active(row=row)
    return rotate_tokens(row=row)
