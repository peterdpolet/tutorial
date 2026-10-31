"""
Episode 5: Logout.

The person presses "Log out". The server ends their login so the refresh token
can never be used again.

    logout_view (views.py)            reads the request, shapes the reply
      -> logout                       the one entry point; runs the steps below
           1. find_logout_session     which login does this refresh token belong to?
           2. end_login               end THIS login (the token's whole family)
              or end_all_logins       "log out everywhere": every login of the user

Three deliberate choices, each visible in the trace:

  * The refresh token is the proof. Logging out needs no password and no access
    token, only the secret that would otherwise keep the login alive.
  * Logout always answers 200, even for a token we do not know or one already
    logged out. A page that presses the button twice, or whose session was
    already ended, should not see an error; and an unknown-token answer must
    not tell a stranger which tokens exist.
  * Ending a login means ending its whole FAMILY (episode 4), not just the one
    token presented, so a rotated-away token cannot be used afterwards either.

What logout CANNOT do: recall the access token. It is a signed note the server
does not look up, so it keeps working until its 15 minutes are up. That is why
access tokens are short.
"""
from django.utils import timezone

from tracker.tracker import checkpoint, traced

from .models import RefreshToken
from .tokens import hash_refresh_token


@traced("find_logout_session")
def find_logout_session(*, refresh_token):
    row = (
        RefreshToken.objects.select_related("user")
        .filter(token_hash=hash_refresh_token(refresh_token))
        .first()
    )
    checkpoint("logout_lookup", found=row is not None)
    return row


@traced("end_login")
def end_login(*, row):
    revoked = RefreshToken.objects.filter(family=row.family, revoked_at__isnull=True).update(
        revoked_at=timezone.now()
    )
    checkpoint("login_ended", revoked_rows=revoked)


@traced("end_all_logins")
def end_all_logins(*, user):
    revoked = RefreshToken.objects.filter(user=user, revoked_at__isnull=True).update(
        revoked_at=timezone.now()
    )
    checkpoint("all_logins_ended", revoked_rows=revoked)


@traced("logout")
def logout(*, refresh_token, everywhere):
    row = find_logout_session(refresh_token=refresh_token)
    if row is None:
        return                      # nothing to end; still a success for the caller
    if everywhere:
        end_all_logins(user=row.user)
    else:
        end_login(row=row)
