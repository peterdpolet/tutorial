"""
Delete stored traces older than N days (default 7).

Traces hold real values from live requests, so they should not live forever.
Run this on a schedule. Each run's header row and all of its events are removed.

    python manage.py prune_traces --days 7
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from tracker.models import RuntimeEvent, TraceRun


class Command(BaseCommand):
    help = "Delete stored traces older than --days (default 7)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7)

    def handle(self, *args, days, **options):
        cutoff = timezone.now() - timedelta(days=days)
        old_ids = [str(pk) for pk in TraceRun.objects.filter(started_at__lt=cutoff).values_list("pk", flat=True)]
        removed = 0
        for i in range(0, len(old_ids), 500):  # chunks: SQLite caps the size of an IN (...) list
            chunk = old_ids[i:i + 500]
            removed += RuntimeEvent.objects.filter(transaction_id__in=chunk).delete()[0]
            removed += TraceRun.objects.filter(pk__in=chunk).delete()[0]
        self.stdout.write(f"Pruned traces older than {days} days ({len(old_ids)} runs, {removed} rows removed).")
