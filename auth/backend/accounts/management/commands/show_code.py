"""
Print the six-digit code an authenticator app would show right now, so you can
follow episode 7 without a phone.

    python manage.py show_code --email learner@example.com

Development only: it refuses to run unless DEBUG is on. (A real server never
needs this, and must never have it.)
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.models import TotpDevice
from accounts.totp import STEP_SECONDS, code_for, current_step
import time


class Command(BaseCommand):
    help = "Print the current one-time code for an account (development only)."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)

    def handle(self, *args, email, **options):
        if not settings.DEBUG:
            raise CommandError("show_code only runs while DEBUG is on.")
        device = TotpDevice.objects.filter(user__username=email.strip().lower()).first()
        if device is None:
            raise CommandError("That account has not started two-factor setup.")
        left = STEP_SECONDS - int(time.time()) % STEP_SECONDS
        self.stdout.write(f"{code_for(device.secret, current_step())}   (changes in {left} seconds)")
