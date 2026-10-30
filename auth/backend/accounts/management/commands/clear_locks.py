"""
Forget all failed-login counts and locks, so you can try the lockout again
without waiting LOGIN_LOCK_MINUTES.

    python manage.py clear_locks

Development only: it refuses to run unless DEBUG is on.
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.models import LoginLock


class Command(BaseCommand):
    help = "Delete every failed-login count and lock (development only)."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("clear_locks only runs while DEBUG is on.")
        count, _ = LoginLock.objects.all().delete()
        self.stdout.write(f"{count} lock record(s) cleared.")
