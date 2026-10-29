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
