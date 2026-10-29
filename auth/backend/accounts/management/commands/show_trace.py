"""
Print a saved trace as an indented story in the terminal.

    python manage.py show_trace            # the latest run
    python manage.py show_trace <run id>   # a particular run (the id the page shows)

Why this exists: the trace viewer's web address only answers logged-in staff,
and in episode 1 nobody can log in yet. This reads the same saved trace
straight from the database, so you can see what happened right away.
(It belongs in the tracker itself and will move there.)
"""
from django.core.management.base import BaseCommand, CommandError

from tracker.models import TraceRun
from tracker.persist import build_tree


def lines(node, depth=0):
    pad = "  " * depth
    args = ", ".join(f"{k}={v}" for k, v in node["args"].items())
    yield f"{pad}{node['name']}({args})"
    for cp in node["checkpoints"]:
        vals = ", ".join(f"{k}={v}" for k, v in cp["values"].items())
        yield f"{pad}  . {cp['label']}" + (f"  [{vals}]" if vals else "")
    for child in node["children"]:
        yield from lines(child, depth + 1)
    if node["exception"]:
        yield f"{pad}  ! {node['exception']}"
    elif node["returned"] is not None:
        yield f"{pad}  -> {node['returned']}"


class Command(BaseCommand):
    help = "Print a saved trace as an indented tree (latest run if no id is given)."

    def add_arguments(self, parser):
        parser.add_argument("run_id", nargs="?")

    def handle(self, *args, run_id=None, **options):
        runs = TraceRun.objects.all()
        try:
            run = runs.get(pk=run_id) if run_id else runs.order_by("-started_at").first()
        except (TraceRun.DoesNotExist, ValueError, Exception) as exc:
            raise CommandError(f"No such run: {run_id}") from exc
        if run is None:
            raise CommandError("No traces saved yet. Send a request with the X-Tracker: 1 header.")
        tree = build_tree(run)
        self.stdout.write(f"{tree['method']} {tree['path']}  ->  {tree['status_code']}  ({run.pk})")
        for root in tree["calls"]:
            for line in lines(root, 1):
                self.stdout.write(line)
