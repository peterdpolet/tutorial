"""
Loading and querying the static code graph (what the discoverer found).

The graph is plain JSON produced by `discover/discover.py`. `load_graph` stores it
in this app's own tables, per project, replacing whatever was there before so a
re-run always gives a clean picture. The queries here join that picture to the
runtime traces: `match_request` turns a recorded request (method + path) into the
view method that handled it, and `flow` walks outwards from any entity.
"""
import re
from collections import deque

from django.db import transaction

from .models import CodeEntity, CodeRelation


class GraphError(ValueError):
    pass


def load_graph(data: dict, project: str | None = None) -> dict:
    """Replace the stored graph for one project with `data`. All or nothing."""
    if not isinstance(data, dict) or "entities" not in data or "relations" not in data:
        raise GraphError("Not a graph file: expected 'entities' and 'relations'.")
    project = project or data.get("project")
    if not project:
        raise GraphError("No project name: put one in the graph file or pass it explicitly.")

    entities, seen = [], set()
    for e in data["entities"]:
        if e["id"] in seen:
            continue  # the discoverer should not emit duplicates; keep the first
        seen.add(e["id"])
        entities.append(
            CodeEntity(
                project=project,
                entity_id=e["id"],
                kind=e.get("kind", ""),
                name=e.get("name", ""),
                file=e.get("file") or "",
                line=e.get("line"),
                language=e.get("language") or "",
                framework=e.get("framework") or "",
                parent_id=e.get("parent_id"),
                docstring=e.get("docstring") or "",
                extra=e.get("extra") or {},
            )
        )
    relations = [
        CodeRelation(
            project=project,
            source_id=r["source_id"],
            target_id=r["target_id"],
            relation_type=r["relation_type"],
            extra=r.get("extra") or {},
        )
        for r in data["relations"]
        if r["source_id"] in seen and r["target_id"] in seen  # no dangling edges
    ]
    with transaction.atomic():
        CodeRelation.objects.filter(project=project).delete()
        CodeEntity.objects.filter(project=project).delete()
        CodeEntity.objects.bulk_create(entities, batch_size=500)
        CodeRelation.objects.bulk_create(relations, batch_size=500)
    return {"project": project, "entities": len(entities), "relations": len(relations),
            "dropped_relations": len(data["relations"]) - len(relations)}


def entity_dict(e: CodeEntity) -> dict:
    return {"id": e.entity_id, "kind": e.kind, "name": e.name, "file": e.file, "line": e.line,
            "language": e.language, "framework": e.framework, "parent_id": e.parent_id,
            "docstring": e.docstring, "extra": e.extra}


def relation_dict(r: CodeRelation) -> dict:
    return {"source_id": r.source_id, "target_id": r.target_id,
            "relation_type": r.relation_type, "extra": r.extra}


def graph(project: str) -> dict:
    return {
        "project": project,
        "entities": [entity_dict(e) for e in CodeEntity.objects.filter(project=project).order_by("entity_id")],
        "relations": [relation_dict(r) for r in CodeRelation.objects.filter(project=project)],
    }


def flow(project: str, start: str) -> dict | None:
    """Everything reachable from `start` by following relations outwards."""
    entities = {e.entity_id: e for e in CodeEntity.objects.filter(project=project)}
    if start not in entities:
        return None
    outgoing = {}
    for r in CodeRelation.objects.filter(project=project):
        outgoing.setdefault(r.source_id, []).append(r)
    reached, edges, queue = {start}, [], deque([start])
    while queue:
        cur = queue.popleft()
        for r in outgoing.get(cur, []):
            edges.append(r)
            if r.target_id not in reached:
                reached.add(r.target_id)
                queue.append(r.target_id)
    return {
        "project": project,
        "start": start,
        "entities": [entity_dict(entities[i]) for i in sorted(reached)],
        "relations": [relation_dict(r) for r in edges],
    }


def _pattern_regex(pattern: str):
    parts = re.split(r"<[^>]+>", pattern)
    return re.compile("(?:^|/)" + "[^/]+".join(re.escape(p) for p in parts).lstrip("/") + "$")


def match_request(project: str, method: str, path: str) -> dict | None:
    """
    Which url entity (and so which view method) handles `method path`?
    The recorded path carries a mount prefix such as /api, which the url entity
    does not, so the pattern is matched against the END of the path. Where several
    match, the most specific (longest) pattern wins, and a route that names its
    methods must include this one.
    """
    path = path.split("?")[0]
    best = None
    for e in CodeEntity.objects.filter(project=project, kind="url"):
        methods = [m.upper() for m in e.extra.get("methods", [])]
        if methods and method.upper() not in methods:
            continue
        if _pattern_regex(e.name).search(path):
            if best is None or len(e.name) > len(best.name):
                best = e
    if best is None:
        return None
    targets = list(CodeRelation.objects.filter(project=project, source_id=best.entity_id,
                                               relation_type="routes_to"))
    return {"url": entity_dict(best), "handlers": [t.target_id for t in targets]}
