"""
Make the emailed links look older, so you can see an expired link without
waiting a day.

    python manage.py age_tokens --hours 50

Development only: it refuses to run unless DEBUG is on.
"""
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import EmailToken


class Command(BaseCommand):
    help = "Move every unused confirmation link's creation time back by N hours (development only)."

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=float, required=True)

    def handle(self, *args, hours, **options):
        if not settings.DEBUG:
            raise CommandError("age_tokens only runs while DEBUG is on.")
        older = timezone.now() - timedelta(hours=hours)
        count = EmailToken.objects.filter(used_at__isnull=True).update(created_at=older)
        self.stdout.write(f"{count} unused link(s) now {hours:g} hours old.")
