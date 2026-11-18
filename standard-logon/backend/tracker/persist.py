"""
Save a finished Trace, and read one back as a nested tree.

Writing reuses the proven pieces from persistence.py / persistence_django.py
(_flatten_trace and write_trace_django). It happens ONCE, after the response
has been produced, in a single transaction: one bulk insert of the events and
one header row. Nothing is written while the traced code is running, so
tracing adds no database waits to the request itself.
"""
from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import RuntimeEvent, TraceRun
from .persistence_django import write_trace_django
from .redaction import redact_text


def save_trace(trace, *, method, path, status_code, duration_ms, user_id=None) -> TraceRun:
    started = datetime.fromtimestamp(trace.started_at, tz=timezone.get_current_timezone())
    with transaction.atomic():
        event_count = write_trace_django(trace, created_by_id=user_id)
        return TraceRun.objects.create(
            id=trace.transaction_id,
            started_at=started,
            method=method[:10],
            path=redact_text(path)[:500],
            status_code=status_code,
            duration_ms=round(duration_ms, 3),
            user_id=user_id,
            event_count=event_count,
        )


def run_summary(run) -> dict:
    return {
        "id": str(run.id),
        "started_at": run.started_at.isoformat(),
        "method": run.method,
        "path": run.path,
        "status_code": run.status_code,
        "duration_ms": run.duration_ms,
        "event_count": run.event_count,
    }


def _ms(value) -> float:
    return float(value) if isinstance(value, Decimal) else (value or 0.0)


def build_tree(run) -> dict:
    """The run plus its calls as nested dicts, ready to send as JSON."""
    calls = {}
    roots = []
    # Parents are always numbered before their children, so one pass in seq
    # order always finds the parent already built.
    for e in RuntimeEvent.objects.filter(transaction_id=str(run.pk)).order_by("seq"):
        if e.event_type == "call":
            node = {
                "seq": e.seq,
                "name": e.qualname,
                "args": e.args_json or {},
                "returned": e.return_repr,
                "exception": e.exception_repr,
                "elapsed_ms": _ms(e.elapsed_ms),
                "checkpoints": [],
                "children": [],
            }
            calls[e.seq] = node
            if e.parent_seq is None:
                roots.append(node)
            else:
                calls[e.parent_seq]["children"].append(node)
        else:
            calls[e.parent_seq]["checkpoints"].append(
                {"seq": e.seq, "label": e.label, "values": e.values_json or {}, "elapsed_ms": _ms(e.elapsed_ms)}
            )
    return {**run_summary(run), "calls": roots}
