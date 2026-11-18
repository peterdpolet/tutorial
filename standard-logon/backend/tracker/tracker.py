"""
Tracker II — proof-of-concept capture mechanism.

Design intent (per the spec worked out in /areas/spadework-companion.md):
- Live capture on the ORIGINAL request (not replay) — required because the
  target use case includes non-idempotent writes (convert_to_po etc.)
- Both "which functions ran, in what order" (cheap, structural) AND
  key intermediate values/branches within a function (richer, opt-in per
  checkpoint) — Peter's call today: go for the richer version.
- Branch-taken tracking (every if/else) explicitly CUT from v1 — this is
  NOT that. This only records what the developer explicitly marks with a
  checkpoint() call, not every branch automatically.
- Capture must be OFF by default (near-zero cost when not tracing) and
  switched on per-transaction via a flag — this matches the "auth-gated,
  deliberate, rare" prod policy already agreed.

This file is deliberately framework-agnostic (no Django/DRF import) so the
mechanism itself can be inspected and reasoned about on its own, before
wiring it into a real view.
"""
import contextvars
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .redaction import redact_if_sensitive, redact_text, scrub_sensitive_keys, REDACTED


# ---------------------------------------------------------------------------
# The transaction context. contextvars (not thread-locals) is the correct
# choice here because Django/Channels code can be async (Daphne is already
# in this stack for chat) — contextvars propagates correctly across
# async/await in a way thread-locals do not.
# ---------------------------------------------------------------------------
_current_trace: contextvars.ContextVar = contextvars.ContextVar(
    "tracker_current_trace", default=None
)


@dataclass
class Checkpoint:
    seq: int
    label: str
    values: dict
    elapsed_ms: float


@dataclass
class FunctionCall:
    seq: int
    qualname: str          # e.g. "SupplierQuote.convert_to_po"
    args_repr: dict
    checkpoints: list = field(default_factory=list)
    return_repr: Any = None
    exception_repr: str | None = None
    elapsed_ms: float = 0.0
    children: list = field(default_factory=list)


class Trace:
    """
    Holds everything captured for one live transaction. This is the
    in-memory shape; persistence to a real runtime_events table is a
    separate concern (see notes at the bottom of this file) — kept
    separate deliberately so the capture mechanism can be tested and
    reasoned about without a database in the loop at all.
    """
    def __init__(self, transaction_id: str):
        self.transaction_id = transaction_id
        self.started_at = time.time()
        self.root_calls: list[FunctionCall] = []
        self._stack: list[FunctionCall] = []
        self._seq = 0

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def enter_call(self, qualname: str, args_repr: dict) -> FunctionCall:
        call = FunctionCall(seq=self._next_seq(), qualname=qualname, args_repr=args_repr)
        if self._stack:
            self._stack[-1].children.append(call)
        else:
            self.root_calls.append(call)
        self._stack.append(call)
        return call

    def exit_call(self, call: FunctionCall, return_repr: Any, exception_repr: str | None, elapsed_ms: float):
        call.return_repr = return_repr
        call.exception_repr = exception_repr
        call.elapsed_ms = elapsed_ms
        # unwind to this call (defensive — should already be top of stack)
        while self._stack and self._stack[-1] is not call:
            self._stack.pop()
        if self._stack:
            self._stack.pop()

    def add_checkpoint(self, label: str, values: dict, elapsed_ms: float):
        if not self._stack:
            return  # checkpoint() called outside any traced() call — ignored, not an error
        cp = Checkpoint(seq=self._next_seq(), label=label, values=values, elapsed_ms=elapsed_ms)
        self._stack[-1].checkpoints.append(cp)


def start_trace(transaction_id: str | None = None) -> Trace:
    """Call this once, at the very top of a request (middleware), only when
    capture has been switched on for this request. If never called, all
    traced()/checkpoint() calls below are cheap no-ops (see is_active())."""
    trace = Trace(transaction_id or str(uuid.uuid4()))
    _current_trace.set(trace)
    return trace


def is_active() -> bool:
    return _current_trace.get() is not None


def current_trace() -> Trace | None:
    return _current_trace.get()


def safe_repr(value: Any, max_len: int = 300, name: str = "") -> Any:
    """
    Capturing 'values' means capturing REAL data — this is where the prod
    retention/redaction concern from the spec actually has to be enforced,
    not just talked about.
    - Django model instances -> a short tag, not a full field dump
      (avoids accidentally serializing every field on every model touched)
    - everything else -> repr(), truncated, then passed through the
      redaction policy (redact_if_sensitive) which checks the kwarg/field
      NAME against a blocklist AND pattern-sniffs the value itself (looks
      like an email, a card number, etc) — see redaction.py for the full
      policy and its honestly-flagged gaps (human names/addresses are NOT
      caught by either check).
    - then sensitive dict KEYS inside containers are scrubbed (on a copy),
      because "hunter2" has no shape that gives it away, only its key does.
    - finally, redact_text() removes sensitive pieces found INSIDE longer
      text (a sentence, or the repr of a list/dict), which the whole-value
      checks above cannot see.
    """
    try:
        cls_name = type(value).__name__
        if hasattr(value, "_meta") and hasattr(value, "pk"):
            return f"<{cls_name} pk={value.pk}>"

        # True / False / None carry no secret beyond yes / no / absent, and
        # flags such as has_token=False are exactly what a trace is for.
        # Exempt them from the NAME blocklist. (Only the real bool/None: the
        # string "True" under a sensitive name is still redacted.)
        if value is None or isinstance(value, bool):
            return repr(value)

        # Redact against the RAW value first when it's a plain string, so
        # pattern-sniffing sees '+44 7911 123456', not the repr()'d
        # "'+44 7911 123456'" with literal quote characters, which breaks
        # anchored regexes. Found via the redaction proof run itself: an
        # earlier version called repr() before redaction, which silently
        # let phone numbers through for exactly this reason — a real bug
        # the proof caught, not a hypothetical one.
        check_value = value if isinstance(value, str) else repr(value)
        redacted = redact_if_sensitive(name, check_value)
        if redacted.startswith(REDACTED):
            return redacted

        # The whole-value check above only catches a value that IS an email,
        # phone number etc. Sensitive data can also sit INSIDE a longer
        # string, a list or a dict's repr, so run the inline redaction too.
        # Redact FIRST, truncate SECOND (see safe_exception_repr for why).
        # scrub_sensitive_keys() works on a COPY (real data is never touched)
        # and hides values under sensitive dict keys such as "password".
        r = redact_text(repr(scrub_sensitive_keys(value)))
        if len(r) > max_len:
            r = r[:max_len] + "…"
        return r
    except Exception as e:  # never let capture itself break the real request
        return f"<unrepr: {e}>"


def safe_exception_repr(exc: BaseException, max_len: int = 300) -> str:
    """
    The exception text recorded on a failed call. Exception messages are
    free text and routinely contain real data (e.g. "no such customer:
    jane@example.com"), so they MUST go through redaction before storage,
    exactly like args and return values do via safe_repr().

    Order matters: redact FIRST, truncate SECOND. Truncating first could cut
    an email in half ("jane@exam"), leaving a fragment that no longer matches
    the pattern and so slips through unredacted.
    """
    try:
        text = redact_text(f"{type(exc).__name__}: {exc}")
        if len(text) > max_len:
            text = text[:max_len] + "…"
        return text
    except Exception as e:  # never let capture itself break the real request
        return f"{type(exc).__name__}: <unrepr: {type(e).__name__}>"


def traced(qualname: str | None = None):
    """
    Decorator: wraps a function/method so that, IF a trace is active for
    this request, its call is recorded (args, return value, exceptions,
    timing) as a node in the call tree. If no trace is active, this is a
    near-zero-cost passthrough (one contextvar read, no dict/object
    allocation) — this is the mechanism that keeps normal untraced
    requests cheap, per the spec's dev/prod cost concern.
    """
    def decorator(fn):
        name = qualname or fn.__qualname__

        def wrapper(*args, **kwargs):
            trace = _current_trace.get()
            if trace is None:
                return fn(*args, **kwargs)  # <-- the cheap path, no tracing

            args_repr = {}
            # skip 'self' position for readability; still shown via qualname
            for i, a in enumerate(args[1:] if args else []):
                args_repr[f"arg{i}"] = safe_repr(a, name=f"arg{i}")
            for k, v in kwargs.items():
                args_repr[k] = safe_repr(v, name=k)

            call = trace.enter_call(name, args_repr)
            t0 = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
            except Exception as e:
                elapsed = (time.perf_counter() - t0) * 1000
                trace.exit_call(call, None, safe_exception_repr(e), elapsed)
                raise
            else:
                elapsed = (time.perf_counter() - t0) * 1000
                trace.exit_call(call, safe_repr(result), None, elapsed)
                return result

        wrapper.__name__ = fn.__name__
        wrapper.__wrapped__ = fn
        return wrapper
    return decorator


def checkpoint(label: str, **values):
    """
    The 'reach inside a function' primitive — call this at any point INSIDE
    a @traced function to record intermediate state (e.g. which branch of
    an if/else was taken, and what the values were at that point).

    This is explicitly NOT automatic branch-taken tracking (that's cut from
    v1 per the spec) — it only records what a developer deliberately marks,
    which is the same "scoped opt-in per decision point" approach flagged
    as the realistic option when the feasibility check ruled out blanket
    per-if instrumentation.

    Near-zero cost when untraced, same reasoning as traced() above.
    """
    trace = _current_trace.get()
    if trace is None:
        return
    t0 = time.perf_counter()
    safe_values = {k: safe_repr(v, name=k) for k, v in values.items()}
    elapsed = (time.perf_counter() - t0) * 1000
    trace.add_checkpoint(label, safe_values, elapsed)


# ---------------------------------------------------------------------------
# NOT built yet, deliberately — flagged here rather than glossed over:
#
# 1. Persistence to a real `runtime_events` table (Postgres). This POC keeps
#    everything in-memory on the Trace object. Writing to Postgres inside a
#    live request adds real latency — needs a decision on sync-write-inline
#    vs fire-and-forget (Celery, already in this stack) vs writing once at
#    request end rather than per-checkpoint. Not addressed here.
#
# 2. The auth-gated "should this request even be traced" check + the
#    Django middleware that calls start_trace() before the view runs. Also
#    not addressed here — this file is the mechanism the middleware would
#    call into, not the middleware itself.
#
# 3. Redaction is a real but deliberately limited policy (see redaction.py):
#    it catches emails, card numbers, NI numbers and phone numbers, by field
#    name and by value shape, including inside free text such as exception
#    messages. It does NOT catch human names or addresses (documented gap).
# ---------------------------------------------------------------------------
