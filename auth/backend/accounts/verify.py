"""
Episode 2: Verify email.

The person opens the link in the email and presses "Confirm my email". The
page sends the token in the link; the server decides whether to switch the
account on.

    verify_view (views.py)            reads the request, shapes the reply
      -> verify_email                 the one entry point; runs the steps below
           1. find_token              the token must exist
           2. check_not_used          a link works once
           3. check_not_expired       a link works for EMAIL_TOKEN_LIFETIME_HOURS
           4. activate_and_consume    switch the account on, mark the link used

Same rules as episode 1: every step is @traced, sits at module level and takes
keyword-only arguments, and records a checkpoint at each decision.
"""
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from tracker.tracker import checkpoint, traced

from .models import EmailToken


class VerificationError(Exception):
    """A refusal the person can act on (ask for a new link, or just log in)."""

    def __init__(self, messages):
        super().__init__("; ".join(messages))
        self.messages = list(messages)


@traced("find_token")
def find_token(*, token):
    row = EmailToken.objects.select_related("user").filter(token=token).first()
    checkpoint("token_lookup", found=row is not None)
    if row is None:
        raise VerificationError(["This confirmation link is not valid."])
    return row


@traced("check_not_used")
def check_not_used(*, row):
    used = row.used_at is not None
    checkpoint("used_check", used=used)
    if used:
        raise VerificationError(["This confirmation link has already been used."])


@traced("check_not_expired")
def check_not_expired(*, row):
    age = timezone.now() - row.created_at
    limit_hours = settings.EMAIL_TOKEN_LIFETIME_HOURS
    expired = age.total_seconds() > limit_hours * 3600
    checkpoint("expiry_check", age_hours=round(age.total_seconds() / 3600, 2), limit_hours=limit_hours, expired=expired)
    if expired:
        raise VerificationError(["This confirmation link has expired."])


@traced("activate_and_consume")
def activate_and_consume(*, row):
    with transaction.atomic():
        # Claim the link in ONE database step. If two clicks arrive together,
        # only one of them updates a row; the other finds it already used.
        claimed = EmailToken.objects.filter(pk=row.pk, used_at__isnull=True).update(used_at=timezone.now())
        checkpoint("link_claimed", claimed=claimed)
        if not claimed:
            raise VerificationError(["This confirmation link has already been used."])
        row.user.is_active = True
        row.user.save(update_fields=["is_active"])
        checkpoint("user_activated", user_id=row.user.pk)


@traced("verify_email")
def verify_email(*, token):
    row = find_token(token=token)
    check_not_used(row=row)
    check_not_expired(row=row)
    activate_and_consume(row=row)
    return row.user
