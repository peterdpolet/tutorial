"""
Load a code graph (the JSON the discoverer writes) into the database.

    python manage.py load_graph path/to/graph.json [--project NAME]

Replaces the stored graph for that project. Safe to re-run.
"""
import json

from django.core.management.base import BaseCommand, CommandError

from tracker.graph import GraphError, load_graph


class Command(BaseCommand):
    help = "Load a discoverer graph.json, replacing the stored graph for its project."

    def add_arguments(self, parser):
        parser.add_argument("graph_file")
        parser.add_argument("--project", default=None)

    def handle(self, *args, graph_file, project, **options):
        try:
            with open(graph_file, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Cannot read {graph_file}: {exc}")
        try:
            result = load_graph(data, project)
        except GraphError as exc:
            raise CommandError(str(exc))
        msg = f"Loaded {result['entities']} entities and {result['relations']} relations for '{result['project']}'."
        if result["dropped_relations"]:
            msg += f" ({result['dropped_relations']} relations pointed at unknown entities and were skipped.)"
        self.stdout.write(self.style.SUCCESS(msg))
