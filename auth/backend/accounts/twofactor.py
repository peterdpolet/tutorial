"""
Episode 7: Two-factor (a code from an authenticator app).

Two flows. The first turns two-factor ON for an account that is already logged
in. The second changes how every later login ends.

  A. turn it on  (the person is logged in; the access token proves who)

    two_factor_setup_view (views.py)
      -> start_setup                  make a secret; show it ONCE; not yet switched on
    two_factor_confirm_view (views.py)
      -> confirm_two_factor           the person types the code their app now shows
           1. find_pending_device     there must be a setup waiting
           2. check_setup_code        the code must match the secret
           3. switch_on               from now on, login asks for a code
           4. issue_recovery_codes    one-use codes for a lost phone, shown ONCE

  B. log in with a code  (login.py hands back an mfa_token instead of tokens)

    two_factor_login_view (views.py)
      -> complete_login               the one entry point; runs the steps below
           1. read_mfa_token          the "password was right" note: genuine, fresh, whose?
           2. check_not_locked        the SAME lock as the password step (login.py)
           3. check_second_factor     a six-digit code, or a recovery code
                use_totp_code         the code must match AND be newer than the last one used
                use_recovery_code     the code must exist and be unused
                (on a miss: record_failure, the SAME failure count as the password step)
           4. reset_failures          only now does a good login wipe the count
           5. issue_tokens            the access and refresh tokens (login.py)

Four deliberate choices, each visible in the trace:

  * Switch on only after a code works. Otherwise a typo while copying the secret
    would lock the person out of their own account on the next login.
  * The password step does NOT wipe the failure count when a second step is
    required. If it did, someone who knows the password could guess codes
    forever: five wrong codes, log in again with the password (count back to
    zero), five more. This is the step the planted bug removes.
  * A code works once. Within its 30 seconds a stolen or over-the-shoulder code
    is useless after the real person has used it.
  * Every wrong code (wrong, replayed, expired, bad recovery code) gets the same
    reply, so the reply does not help a guesser.
"""
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.db import transaction
from django.utils import timezone

from tracker.tracker import checkpoint, traced

from .login import LoginError, check_not_locked, issue_tokens, record_failure, reset_failures
from .models import RecoveryCode, TotpDevice
from .tokens import MFA_SALT, hash_secret
from .totp import current_step, looks_like_a_code, matching_step, new_secret, provisioning_uri

User = get_user_model()

BAD_CODE = "That code is not right."


# ---- A. turn it on ----------------------------------------------------------

@traced("start_setup")
def start_setup(*, user):
    existing = TotpDevice.objects.filter(user=user).first()
    on = bool(existing and existing.confirmed_at)
    checkpoint("device_lookup", has_device=existing is not None, already_on=on)
    if on:
        raise LoginError(409, "Two-factor is already on for this account.")
    secret = new_secret()
    # A second setup before confirming simply replaces the first secret.
    TotpDevice.objects.update_or_create(
        user=user, defaults={"secret": secret, "confirmed_at": None, "last_used_step": 0})
    checkpoint("setup_started")
    return {"secret": secret, "otpauth_uri": provisioning_uri(secret, user.username, settings.TOTP_ISSUER)}


@traced("find_pending_device")
def find_pending_device(*, user):
    device = TotpDevice.objects.filter(user=user).first()
    pending = device is not None and device.confirmed_at is None
    checkpoint("pending_lookup", found=device is not None, pending=pending)
    if device is None:
        raise LoginError(400, "Start setup first.")
    if not pending:
        raise LoginError(409, "Two-factor is already on for this account.")
    return device


@traced("check_setup_code")
def check_setup_code(*, device, otp_code):
    step = matching_step(device.secret, otp_code, after_step=0)
    checkpoint("code_check", matched=step is not None)
    if step is None:
        raise LoginError(400, BAD_CODE + " Check the clock on your phone and try the next code.")
    return step


@traced("switch_on")
def switch_on(*, device, step):
    device.confirmed_at = timezone.now()
    device.last_used_step = step           # the code just typed cannot be used again to log in
    device.save(update_fields=["confirmed_at", "last_used_step"])
    checkpoint("two_factor_on", user_id=device.user_id)


@traced("issue_recovery_codes")
def issue_recovery_codes(*, user):
    codes = [secrets.token_hex(5) for _ in range(settings.RECOVERY_CODE_COUNT)]
    with transaction.atomic():
        RecoveryCode.objects.filter(user=user).delete()
        RecoveryCode.objects.bulk_create([RecoveryCode(user=user, code_hash=hash_secret(c)) for c in codes])
    checkpoint("recovery_issued", count=len(codes))
    # Returned under a NAME on purpose. The tracker hides values by the name they
    # travel under, and a bare list has no name: the codes would be stored in the
    # trace. (The redaction audit test caught exactly that.)
    return {"recovery_codes": [f"{c[:5]}-{c[5:]}" for c in codes]}


@traced("confirm_two_factor")
def confirm_two_factor(*, user, otp_code):
    device = find_pending_device(user=user)
    step = check_setup_code(device=device, otp_code=otp_code)
    switch_on(device=device, step=step)
    return issue_recovery_codes(user=user)


# ---- B. log in with a code --------------------------------------------------

@traced("read_mfa_token")
def read_mfa_token(*, mfa_token):
    try:
        data = signing.loads(mfa_token, salt=MFA_SALT, max_age=settings.MFA_TOKEN_SECONDS)
    except signing.SignatureExpired:
        checkpoint("mfa_token_check", valid=False, why="expired")
        raise LoginError(401, "That took too long. Log in again.")
    except signing.BadSignature:
        checkpoint("mfa_token_check", valid=False, why="bad_signature")
        raise LoginError(401, "Log in again.")
    user = User.objects.filter(pk=data.get("uid"), is_active=True).first()
    checkpoint("mfa_token_check", valid=user is not None, why="ok" if user else "no_such_user")
    if user is None:
        raise LoginError(401, "Log in again.")
    return user


@traced("use_totp_code")
def use_totp_code(*, user, otp_code):
    device = TotpDevice.objects.filter(user=user, confirmed_at__isnull=False).first()
    if device is None:
        checkpoint("totp_check", has_device=False, matched=False)
        return False
    # Does the code match ANY recent step? Then: is that step one we have already used?
    step = matching_step(device.secret, otp_code, after_step=0)
    replayed = step is not None and step <= device.last_used_step
    claimed = 0
    if step is not None and not replayed:
        # Claim the step in ONE database step, as episodes 2 and 6 claim a link: if two
        # requests carry the same code together, only one updates a row.
        claimed = TotpDevice.objects.filter(pk=device.pk, last_used_step__lt=step).update(last_used_step=step)
    # matched = the digits are right for a recent step; replayed = but that step was already
    # used; claimed = 1 only when the code was right AND new. A wrong code and a replayed code
    # look different here, which is the whole point of writing the decision down.
    checkpoint("totp_check", has_device=True, matched=step is not None, replayed=replayed, claimed=claimed)
    return bool(claimed)


@traced("use_recovery_code")
def use_recovery_code(*, user, otp_code):
    cleaned = otp_code.strip().lower().replace("-", "").replace(" ", "")
    used = RecoveryCode.objects.filter(
        user=user, code_hash=hash_secret(cleaned), used_at__isnull=True).update(used_at=timezone.now())
    left = RecoveryCode.objects.filter(user=user, used_at__isnull=True).count()
    checkpoint("recovery_check", used=bool(used), codes_left=left)
    return bool(used)


@traced("check_second_factor")
def check_second_factor(*, user, otp_code):
    typed = otp_code.strip().replace(" ", "")
    ok = use_totp_code(user=user, otp_code=typed) if looks_like_a_code(typed) else use_recovery_code(user=user, otp_code=otp_code)
    if not ok:
        record_failure(email=user.username)       # the same count and lock as a wrong password
        raise LoginError(401, BAD_CODE)


@traced("complete_login")
def complete_login(*, mfa_token, otp_code):
    user = read_mfa_token(mfa_token=mfa_token)
    check_not_locked(email=user.username)
    check_second_factor(user=user, otp_code=otp_code)
    reset_failures(email=user.username)
    return issue_tokens(user=user)
