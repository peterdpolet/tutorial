"""
The two kinds of token, made in one place.

Login (episode 3) and refresh (episode 4) both hand out an access token and a
refresh token. Keeping the recipe here means they cannot drift apart.

  access token   a signed note "user 7" that expires in ACCESS_TOKEN_SECONDS.
                 The server checks the signature; it stores nothing.
  refresh token  a random secret. Only its SHA-256 hash is stored, so a copy of
                 the database cannot be used to log in as anyone.
"""
import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.utils import timezone

from .models import RefreshToken

ACCESS_SALT = "auth-tutorial.access"


def hash_refresh_token(refresh_token):
    return hashlib.sha256(refresh_token.encode()).hexdigest()


def make_access_token(user):
    return signing.dumps({"uid": user.pk}, salt=ACCESS_SALT)


def new_family():
    return secrets.token_hex(8)


def store_refresh_token(user, family):
    """Create the next refresh token in `family`; return the secret (the only copy)."""
    refresh_token = secrets.token_urlsafe(32)
    RefreshToken.objects.create(
        user=user,
        family=family,
        token_hash=hash_refresh_token(refresh_token),
        expires_at=timezone.now() + timedelta(days=settings.REFRESH_TOKEN_DAYS),
    )
    return refresh_token
