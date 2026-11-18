"""
Real Django ORM persistence functions — the version to actually run
against emillar_db. Supersedes write_trace_sqlite/read_trace_rows_sqlite
in persistence.py, which exist only to prove the schema/flatten logic
without a Postgres instance available in the dev sandbox.

Requires: the RuntimeEvent model + migration from 0001_initial_migration.py
actually applied to a real database first (`python manage.py migrate`).

NOT yet run against a real database — written to be a straightforward
ORM-based swap of the already-proven flatten logic, not independently
tested. This is the real next step on Peter's laptop/server, not
something provable further from this environment (no local Postgres
available here).
"""
from .models import RuntimeEvent  # the app name from the migration notes — adjust if different
from .persistence import _flatten_trace  # reuse the exact same, already-proven flatten logic


def write_trace_django(trace, created_by_id=None):
    """
    The real buffered write — call this ONCE, in TrackerTriggerMiddleware,
    after get_response() returns (see trigger.py's comment marking where
    this plugs in). Uses bulk_create for the actual insert: one round trip
    for the whole trace, not one INSERT per row — this is the Django-ORM
    equivalent of persistence.py's executemany() batch insert, so the
    "buffered, once per request" cost decision from the spec is honoured
    here too, not just in the SQLite proof.
    """
    rows = _flatten_trace(trace, created_by_id=created_by_id)
    objects = [
        RuntimeEvent(
            id=r["id"],
            transaction_id=r["transaction_id"],
            seq=r["seq"],
            parent_seq=r["parent_seq"],
            qualname=r["qualname"],
            event_type=r["event_type"],
            label=r["label"],
            args_json=_parse_json_or_none(r["args_json"]),
            return_repr=r["return_repr"],
            exception_repr=r["exception_repr"],
            values_json=_parse_json_or_none(r["values_json"]),
            elapsed_ms=r["elapsed_ms"],
            created_by_id=r["created_by_id"],
        )
        for r in rows
    ]
    RuntimeEvent.objects.bulk_create(objects)
    return len(objects)


def read_trace_rows_django(transaction_id: str):
    """
    Reads a persisted trace back as a list of dicts — SAME SHAPE as
    persistence.py's read_trace_rows_sqlite(), so rows_to_trace_html()
    (already proven) can render either source unchanged. This is the
    point of keeping the row shape identical across both backends: the
    rendering logic doesn't care which database produced the rows.
    """
    qs = RuntimeEvent.objects.filter(transaction_id=transaction_id).order_by("seq")
    return [
        {
            "seq": obj.seq,
            "parent_seq": obj.parent_seq,
            "qualname": obj.qualname,
            "event_type": obj.event_type,
            "label": obj.label,
            "args_json": _dump_json_or_none(obj.args_json),
            "return_repr": obj.return_repr,
            "exception_repr": obj.exception_repr,
            "values_json": _dump_json_or_none(obj.values_json),
            "elapsed_ms": float(obj.elapsed_ms) if obj.elapsed_ms is not None else None,
        }
        for obj in qs
    ]


def _parse_json_or_none(json_str):
    """_flatten_trace() (shared with the SQLite path) produces JSON as
    already-dumped strings, since SQLite has no native JSON type — but
    Django's JSONField wants a real Python object, not a string, or it'll
    store the string ITSELF as a JSON-encoded string (double-encoding).
    This is a real, easy-to-miss bug this exact swap could introduce if
    not handled — flagged and handled here, not left as a trap."""
    import json
    if json_str is None:
        return None
    return json.loads(json_str)


def _dump_json_or_none(value):
    """Inverse of the above, for read: rows_to_trace_html() expects
    values_json/args_json as JSON STRINGS (matching what the SQLite path
    returns, since it reads a TEXT column) — so a JSONField's already-
    parsed Python object needs re-serializing to keep the shared render
    function working unchanged against either source."""
    import json
    if value is None:
        return None
    return json.dumps(value)
