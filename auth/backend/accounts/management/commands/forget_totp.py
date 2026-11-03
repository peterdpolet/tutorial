"""
Turn two-factor off for one account, so an episode-7 demo can be run again.

    python manage.py forget_totp --email learner@example.com

Development only: it refuses to run unless DEBUG is on. (The tutorial has no
"turn it off" screen: a real one would ask for the password and a code.)
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.models import RecoveryCode, TotpDevice


class Command(BaseCommand):
    help = "Delete an account's authenticator secret and recovery codes (development only)."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)

    def handle(self, *args, email, **options):
        if not settings.DEBUG:
            raise CommandError("forget_totp only runs while DEBUG is on.")
        email = email.strip().lower()
        devices, _ = TotpDevice.objects.filter(user__username=email).delete()
        codes, _ = RecoveryCode.objects.filter(user__username=email).delete()
        self.stdout.write(f"Removed {devices} authenticator secret(s) and {codes} recovery code(s).")
