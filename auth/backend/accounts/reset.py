"""
Episode 6: Password reset.

Two requests, because two different things happen.

  A. "I forgot my password"  (the person types only their email)

    forgot_view (views.py)            reads the request, ALWAYS answers the same
      -> request_reset                the one entry point; runs the steps below
           1. normalise_email         tidy the address (same rule as Register, Login)
           2. find_account            is there a confirmed account for it?
           3. check_cooldown          was a link emailed to it a moment ago?
           4. issue_reset_token       make a new secret; retire any older link
           5. send_reset_email        print the email (console, in development)

  B. "Here is my link and my new password"

    reset_view (views.py)             reads the request, shapes the reply
      -> reset_password               the one entry point; runs the steps below
           1. find_reset              the link must exist (and its account be active)
           2. check_reset_not_used    a link works once
           3. check_reset_not_expired a link works for PASSWORD_RESET_LIFETIME_MINUTES
           4. check_new_password      the new password must pass the same rules as Register
           5. apply_reset             ONE transaction: use up the link, set the password,
                                      end every login (end_all_logins, episode 5),
                                      clear the failed-login count (reset_failures, episode 3)

Four deliberate choices, each visible in the trace:

  * Part A answers the SAME words for a known and an unknown address. If it did
    not, the "forgot password" form would tell a stranger which addresses have
    accounts. (Episode 1's register form still does; see the README.)
  * A weak new password is refused BEFORE the link is used up, so the person can
    try again with the same link.
  * Resetting ends every login. The usual reason to reset is "someone else may
    have my password", and a stolen login that survived the reset would make the
    reset pointless. This is the step the planted bug removes.
  * Only the hash of the link is stored. Whoever holds a link can set a password.
"""
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from tracker.tracker import checkpoint, traced

from .login import normalise_email, reset_failures
from .logout import end_all_logins
from .models import ResetToken
from .tokens import hash_secret

User = get_user_model()


class ResetError(Exception):
    """A refusal the person can act on. `field` says which input; `messages` why."""

    def __init__(self, field, messages):
        super().__init__(f"{field}: {'; '.join(messages)}")
        self.field = field
        self.messages = list(messages)


# ---- A. ask for a link ------------------------------------------------------

@traced("find_account")
def find_account(*, email):
    # Only a confirmed account gets a link. An unconfirmed one should use its
    # confirmation link; a deactivated one must not be revived by a reset.
    user = User.objects.filter(username=email, is_active=True).first()
    checkpoint("account_lookup", found=user is not None)
    return user


@traced("check_cooldown")
def check_cooldown(*, user):
    since = timezone.now() - timedelta(seconds=settings.PASSWORD_RESET_COOLDOWN_SECONDS)
    too_soon = ResetToken.objects.filter(user=user, created_at__gt=since).exists()
    checkpoint("cooldown_check", too_soon=too_soon, cooldown_seconds=settings.PASSWORD_RESET_COOLDOWN_SECONDS)
    return too_soon


@traced("issue_reset_token")
def issue_reset_token(*, user):
    secret = secrets.token_urlsafe(32)
    with transaction.atomic():
        # Only the newest link works: retire any older link still unused.
        retired = ResetToken.objects.filter(user=user, used_at__isnull=True).update(used_at=timezone.now())
        row = ResetToken.objects.create(user=user, token_hash=hash_secret(secret))
    checkpoint("reset_issued", row=row.pk, older_links_retired=retired)
    return secret


@traced("send_reset_email")
def send_reset_email(*, user, token):
    link = f"{settings.FRONTEND_URL}/reset?token={token}"
    send_mail(
        subject="Reset your password",
        message=(
            "Someone asked to reset the password for this account. To choose a new one, "
            f"open this link within {settings.PASSWORD_RESET_LIFETIME_MINUTES} minutes:\n\n{link}\n\n"
            "If that was not you, ignore this email: your password has not changed.\n"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )
    checkpoint("email_sent", to_domain=user.email.split("@")[-1])


@traced("request_reset")
def request_reset(*, email):
    email = normalise_email(email=email)
    user = find_account(email=email)
    if user is None:
        return                      # nothing to send; the caller answers exactly as if we had
    if check_cooldown(user=user):
        return                      # a link went out a moment ago; do not mail-bomb the owner
    token = issue_reset_token(user=user)
    send_reset_email(user=user, token=token)


# ---- B. use the link --------------------------------------------------------

@traced("find_reset")
def find_reset(*, token):
    row = (
        ResetToken.objects.select_related("user")
        .filter(token_hash=hash_secret(token), user__is_active=True)
        .first()
    )
    checkpoint("reset_lookup", found=row is not None)
    if row is None:
        raise ResetError("token", ["This reset link is not valid."])
    return row


@traced("check_reset_not_used")
def check_reset_not_used(*, row):
    used = row.used_at is not None
    checkpoint("used_check", used=used)
    if used:
        raise ResetError("token", ["This reset link has already been used."])


@traced("check_reset_not_expired")
def check_reset_not_expired(*, row):
    age = timezone.now() - row.created_at
    limit = settings.PASSWORD_RESET_LIFETIME_MINUTES
    expired = age.total_seconds() > limit * 60
    checkpoint("expiry_check", age_minutes=round(age.total_seconds() / 60, 1), limit_minutes=limit, expired=expired)
    if expired:
        raise ResetError("token", ["This reset link has expired. Ask for a new one."])


@traced("check_new_password")
def check_new_password(*, row, password):
    try:
        validate_password(password, user=row.user)
    except ValidationError as exc:
        checkpoint("password_refused", reasons=len(exc.messages))
        raise ResetError("password", exc.messages)
    checkpoint("password_accepted")


@traced("apply_reset")
def apply_reset(*, row, password):
    with transaction.atomic():
        # Use up the link in ONE database step, as episode 2 does: if two requests
        # arrive together, only one updates a row.
        claimed = ResetToken.objects.filter(pk=row.pk, used_at__isnull=True).update(used_at=timezone.now())
        checkpoint("link_claimed", claimed=claimed)
        if not claimed:
            raise ResetError("token", ["This reset link has already been used."])
        row.user.set_password(password)
        row.user.save(update_fields=["password"])
        checkpoint("password_changed", user_id=row.user.pk)
        end_all_logins(user=row.user)
        reset_failures(email=row.user.username)


@traced("reset_password")
def reset_password(*, token, password):
    row = find_reset(token=token)
    check_reset_not_used(row=row)
    check_reset_not_expired(row=row)
    check_new_password(row=row, password=password)
    apply_reset(row=row, password=password)
    return row.user
