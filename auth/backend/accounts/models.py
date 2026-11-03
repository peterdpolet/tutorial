"""
One new table. The user itself is Django's built-in User.

EmailToken is the single-use secret in the link we email. We store the token
as it was sent (episode 2 will discuss storing a hash instead) and note when
it was made and when it was used, so "expired" and "already used" are both
questions the database can answer.
"""
from django.conf import settings
from django.db import models


class EmailToken(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)


class LoginLock(models.Model):
    """
    Failed-login bookkeeping, one row per email ADDRESS (not per user).

    Keyed by the address the person typed, so an address that has no account
    locks exactly like one that has. If only real accounts locked, the lock
    message would tell an attacker which addresses are registered.
    """
    email = models.CharField(max_length=254, unique=True)
    failed_count = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)


class RefreshToken(models.Model):
    """
    The long-lived half of a login. We keep only a hash of it: if the database
    leaked, the rows would not be usable as logins. Episode 4 spends these:
    each use retires the row (revoked_at) and issues the next one.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    # One login = one family. Each refresh retires a token and issues the next
    # one in the same family, so a whole login can be ended in one step.
    family = models.CharField(max_length=32, db_index=True)
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)


class ResetToken(models.Model):
    """
    The single-use secret in the password-reset link. Like a refresh token, only
    its hash is stored: whoever holds the link can set a new password, so a copy
    of the database must not contain usable links.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)


class TotpDevice(models.Model):
    """
    The authenticator-app secret for one account (episode 7).

    Unlike a password, the secret CANNOT be stored as a hash: the server has to
    compute the same six digits the phone shows, so it needs the secret itself.
    A real system encrypts it at rest (a known limit, see the README).
    confirmed_at stays empty until the person proves the app works by typing a
    code; until then the account does not ask for a second step.
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    secret = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    # The newest 30-second step already accepted. A code from this step, or any
    # earlier one, is refused: a six-digit code works once.
    last_used_step = models.BigIntegerField(default=0)


class RecoveryCode(models.Model):
    """One-use codes for a lost phone. Only the hash is stored, like a refresh token."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    code_hash = models.CharField(max_length=64, unique=True)
    used_at = models.DateTimeField(null=True, blank=True)
