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
    leaked, the rows would not be usable as logins. Episode 4 spends these.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
