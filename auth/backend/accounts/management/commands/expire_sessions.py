"""
Expire every live refresh token, so you can see an expired session without
waiting two weeks.

    python manage.py expire_sessions

Development only: it refuses to run unless DEBUG is on.
"""
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import RefreshToken


class Command(BaseCommand):
    help = "Expire every unrevoked refresh token (development only)."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("expire_sessions only runs while DEBUG is on.")
        count = RefreshToken.objects.filter(revoked_at__isnull=True).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        self.stdout.write(f"{count} live refresh token(s) expired.")
