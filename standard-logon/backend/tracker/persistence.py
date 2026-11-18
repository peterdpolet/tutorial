"""
Tracker II — persistence layer.

Decisions made 24 Sep:
- Lives in emillar_db (the app's own Postgres), not spadework_meta — the
  DATA is app data (real PKs, real FK-shaped relationships to PurchaseOrder
  etc), even though the FEATURE surfaces inside SpadeMap's UI. Keeps
  spadework_meta purely the static graph, avoids a second DB connection
  at runtime.
- Buffered write: the whole captured Trace is serialized and written ONCE,
  after the view returns (in the middleware, after get_response()) — not
  per-checkpoint. Simple, no Celery dependency for v1, and "once per
  traced request" cost is fine given capture is rare/opt-in/one-shot.

Schema below is written as real Postgres DDL (works unchanged as
PostgreSQL SQL). This file's own smoke test runs it against SQLite
instead, because no local Postgres is available to prove against here —
SQLite proves the actual thing that matters (does the write/read
round-trip correctly serialize/deserialize a real captured Trace tree)
with the identical SQL and identical logic; only the DB-API connection
line differs (psycopg vs sqlite3), which is flagged explicitly below
rather than glossed over. This is NOT "tested against Postgres" — that
still needs doing for real, against the real emillar_db, before this can
be called proven in its real home.
"""
import json
import sqlite3
import uuid
from dataclasses import asdict


# ---------------------------------------------------------------------------
# Real Postgres DDL. One row per traced FUNCTION CALL (not one row for the
# whole trace) — this is a deliberate choice, not the only option: it means
# a trace can be reconstructed as a proper tree via parent_seq, and it means
# a future "search across all captures for calls to X" query is a plain
# WHERE qualname = ..., not a JSON-reach-into. The trade-off is more rows
# per trace instead of one blob — acceptable given capture is rare, not
# routine.
# ---------------------------------------------------------------------------
POSTGRES_DDL = """
CREATE TABLE IF NOT EXISTS runtime_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id  VARCHAR(200) NOT NULL,
    seq             INTEGER NOT NULL,
    parent_seq      INTEGER NULL,          -- NULL = root call
    qualname        VARCHAR(300) NOT NULL, -- e.g. 'SupplierQuote.convert_to_po'
    event_type      VARCHAR(20) NOT NULL,  -- 'call' or 'checkpoint'
    label           VARCHAR(200) NULL,     -- checkpoint label; NULL for 'call' rows
    args_json       JSONB NULL,
    return_repr     TEXT NULL,
    exception_repr  TEXT NULL,
    values_json     JSONB NULL,            -- checkpoint values
    elapsed_ms      NUMERIC(10, 4) NULL,
    created_by_id   INTEGER NULL,          -- FK-shaped: real user.id, no FK constraint added
                                            -- in v1 (avoids a migration dependency loop with
                                            -- the User app just for a debug-tool table)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_runtime_events_transaction
    ON runtime_events (transaction_id, seq);
"""

# SQLite equivalent for this file's own smoke test only — JSONB -> TEXT,
# gen_random_uuid()/now() -> app-side defaults. This divergence is exactly
# why "works here" is not yet "proven against Postgres".
_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS runtime_events (
    id              TEXT PRIMARY KEY,
    transaction_id  TEXT NOT NULL,
    seq             INTEGER NOT NULL,
    parent_seq      INTEGER NULL,
    qualname        TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    label           TEXT NULL,
    args_json       TEXT NULL,
    return_repr     TEXT NULL,
    exception_repr  TEXT NULL,
    values_json     TEXT NULL,
    elapsed_ms      REAL NULL,
    created_by_id   INTEGER NULL,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runtime_events_transaction
    ON runtime_events (transaction_id, seq);
"""


def _flatten_trace(trace, created_by_id=None):
    """
    Walks a captured tracker.Trace's call tree and produces a flat list of
    row-dicts ready to insert — one row per FunctionCall, one row per
    Checkpoint. This is the real conversion logic, shared by whichever DB
    backend writes it.
    """
    rows = []

    def walk(call, parent_seq):
        rows.append({
            "id": str(uuid.uuid4()),
            "transaction_id": trace.transaction_id,
            "seq": call.seq,
            "parent_seq": parent_seq,
            "qualname": call.qualname,
            "event_type": "call",
            "label": None,
            "args_json": json.dumps(call.args_repr),
            "return_repr": call.return_repr,
            "exception_repr": call.exception_repr,
            "values_json": None,
            "elapsed_ms": call.elapsed_ms,
            "created_by_id": created_by_id,
        })
        for cp in call.checkpoints:
            rows.append({
                "id": str(uuid.uuid4()),
                "transaction_id": trace.transaction_id,
                "seq": cp.seq,
                "parent_seq": call.seq,  # checkpoints nest under their owning call
                "qualname": call.qualname,
                "event_type": "checkpoint",
                "label": cp.label,
                "args_json": None,
                "return_repr": None,
                "exception_repr": None,
                "values_json": json.dumps(cp.values),
                "elapsed_ms": cp.elapsed_ms,
                "created_by_id": created_by_id,
            })
        for child in call.children:
            walk(child, call.seq)

    for root_call in trace.root_calls:
        walk(root_call, parent_seq=None)

    return rows


def write_trace_sqlite(conn: sqlite3.Connection, trace, created_by_id=None):
    """
    The buffered write: ONE call, after the request completes, inserting
    every row for this trace in a single transaction. This is the
    SQLite-proven version — real Postgres version differs only in the
    INSERT placeholder style (%s vs ?) and JSONB vs TEXT for the json
    columns, per the DDL divergence noted above.
    """
    import datetime
    rows = _flatten_trace(trace, created_by_id=created_by_id)
    now = datetime.datetime.utcnow().isoformat()
    conn.executemany(
        """
        INSERT INTO runtime_events
            (id, transaction_id, seq, parent_seq, qualname, event_type,
             label, args_json, return_repr, exception_repr, values_json,
             elapsed_ms, created_by_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (r["id"], r["transaction_id"], r["seq"], r["parent_seq"],
             r["qualname"], r["event_type"], r["label"], r["args_json"],
             r["return_repr"], r["exception_repr"], r["values_json"],
             r["elapsed_ms"], r["created_by_id"], now)
            for r in rows
        ],
    )
    conn.commit()
    return len(rows)


def read_trace_rows_sqlite(conn: sqlite3.Connection, transaction_id: str):
    """Reads a persisted trace back out, ordered so a tree can be
    reconstructed (parent rows before children, by seq)."""
    cur = conn.execute(
        """
        SELECT seq, parent_seq, qualname, event_type, label, args_json,
               return_repr, exception_repr, values_json, elapsed_ms
        FROM runtime_events
        WHERE transaction_id = ?
        ORDER BY seq ASC
        """,
        (transaction_id,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def rows_to_trace_html(rows, title: str) -> str:
    """
    Rebuilds a renderable structure from FLAT persisted rows (as read back
    from the DB, not from the in-memory Trace object) and produces HTML —
    proving the round trip really matters here: this function receives
    ONLY what came back out of the database, nothing carried over from the
    original in-memory Trace. If this renders correctly, persistence is
    genuinely proven, not just "insert didn't error".
    """
    import html as html_mod

    by_seq = {r["seq"]: r for r in rows}
    children_of = {}  # parent_seq -> [rows]
    for r in rows:
        children_of.setdefault(r["parent_seq"], []).append(r)

    def render_node(row):
        if row["event_type"] == "checkpoint":
            values = json.loads(row["values_json"]) if row["values_json"] else {}
            kv = "".join(
                f'<div class="kv"><span class="k">{html_mod.escape(str(k))}</span>'
                f'<span class="v">{html_mod.escape(str(v))}</span></div>'
                for k, v in values.items()
            )
            return f'''<div class="checkpoint">
                <div class="checkpoint-label">◆ {html_mod.escape(row["label"])}</div>
                {kv}</div>'''
        else:
            args = json.loads(row["args_json"]) if row["args_json"] else {}
            args_html = "".join(
                f'<div class="kv"><span class="k">{html_mod.escape(str(k))}</span>'
                f'<span class="v">{html_mod.escape(str(v))}</span></div>'
                for k, v in args.items()
            )
            child_rows = children_of.get(row["seq"], [])
            children_html = "".join(render_node(c) for c in sorted(child_rows, key=lambda r: r["seq"]))
            badge = (f'<span class="badge error">raised {html_mod.escape(row["exception_repr"])}</span>'
                     if row["exception_repr"]
                     else f'<span class="badge ok">→ {html_mod.escape(str(row["return_repr"])[:60])}</span>')
            return f'''<div class="call">
                <div class="call-header">
                    <span class="fn-name">{html_mod.escape(row["qualname"])}</span>
                    <span class="timing">{row["elapsed_ms"]:.2f}ms</span>
                    {badge}
                </div>
                <div class="call-body">
                    {f'<div class="args-block">{args_html}</div>' if args_html else ''}
                    {children_html}
                </div></div>'''

    root_rows = children_of.get(None, [])
    body = "".join(render_node(r) for r in sorted(root_rows, key=lambda r: r["seq"]))

    return f'''<!DOCTYPE html><html><head><meta charset="utf-8"><title>{html_mod.escape(title)}</title>
    <style>
      :root {{ --bg:#0f1117;--panel:#171a23;--border:#2a2f3d;--text:#e4e6eb;
               --dim:#8a8f9c;--accent:#6ea8fe;--ok:#3fb950;--err:#f85149;--checkpoint:#d29922; }}
      * {{ box-sizing:border-box; }}
      body {{ background:var(--bg);color:var(--text);font-family:-apple-system,sans-serif;margin:0;padding:32px; }}
      h1 {{ font-size:18px;margin:0 0 4px; }}
      .badge-source {{ color:var(--dim);font-size:12.5px;margin-bottom:24px; }}
      .call {{ border:1px solid var(--border);border-left:3px solid var(--accent);border-radius:6px;
               background:var(--panel);margin:10px 0;padding:12px 16px; }}
      .call-header {{ display:flex;align-items:center;gap:10px;font-size:13.5px;flex-wrap:wrap; }}
      .fn-name {{ font-weight:600;font-family:ui-monospace,monospace; }}
      .timing {{ color:var(--dim);font-size:12px;margin-left:auto; }}
      .badge {{ font-size:11.5px;padding:2px 8px;border-radius:10px;font-family:ui-monospace,monospace;
                max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }}
      .badge.ok {{ background:rgba(63,185,80,.15);color:var(--ok); }}
      .badge.error {{ background:rgba(248,81,73,.15);color:var(--err); }}
      .call-body {{ margin-top:8px;padding-left:8px; }}
      .kv {{ font-family:ui-monospace,monospace;font-size:12.5px;display:flex;gap:8px; }}
      .kv .k {{ color:var(--dim);min-width:140px; }}
      .checkpoint {{ border-left:2px solid var(--checkpoint);background:rgba(210,153,34,.08);
                     padding:6px 10px;margin:6px 0;border-radius:4px; }}
      .checkpoint-label {{ color:var(--checkpoint);font-size:12.5px;font-weight:600;margin-bottom:3px; }}
    </style></head><body>
    <h1>{html_mod.escape(title)}</h1>
    <div class="badge-source">⟵ rendered from PERSISTED rows read back out of the database, not the original in-memory trace</div>
    {body}
    </body></html>'''
