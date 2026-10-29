"""
Tracker II — trigger mechanism (arm / fire / disarm).

Real design decisions made 24 Sep, reproduced here:
- Trigger UI SHAPE is a per-user toggle ("flag my next request") — but for
  v1, only superuser/Peter can actually use it (Rebecca tells Peter, Peter
  flags it). Same shape, narrower rollout.
- The flag needs to survive the gap between "toggle clicked" and "the
  flagged request arrives" — a plain request-scoped check can't do that,
  it needs real persisted state. Redis (already in the emillar_v2 stack)
  is the natural fit: fast, already there, and a short TTL naturally
  answers "what if the flag is left on and forgotten" (it expires).
- "Next request" means ONE-SHOT: arming, firing once, then disarming
  automatically — not "trace everything until I remember to turn it off".
  This matches "rare, per-transaction" from the spec, not blanket logging.

This file is deliberately NOT wired to a real redis-py client or a real
Django middleware base class, so it can be run and inspected standalone,
the same way tracker.py was. A `FakeRedis` class stands in for the real
`redis.Redis` — same interface shape (get/set/delete with ex=), so
swapping in the real client later is a one-line change, not a redesign.
"""
import time
from .tracker import start_trace


# ---------------------------------------------------------------------------
# Stand-in for a real Redis connection. Same interface (get/setex/delete)
# that redis-py exposes, so this class is what gets deleted (not rewritten)
# once wired to the real `django_redis`/`redis-py` connection already used
# elsewhere in emillar_v2.
# ---------------------------------------------------------------------------
class FakeRedis:
    def __init__(self):
        self._store = {}  # key -> (value, expires_at)

    def setex(self, key, ttl_seconds, value):
        self._store[key] = (value, time.time() + ttl_seconds)

    def get(self, key):
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.time() > expires_at:
            del self._store[key]
            return None
        return value

    def delete(self, key):
        self._store.pop(key, None)


redis_conn = FakeRedis()  # stand-in; real version: django_redis.get_redis_connection()

ARM_TTL_SECONDS = 5 * 60  # "armed for 5 minutes" — auto-expires if forgotten


def _arm_key(user_id) -> str:
    return f"tracker:armed:{user_id}"


def arm_next_request(user) -> bool:
    """
    Called by the toggle endpoint. Only superusers can arm, per the 24 Sep
    v1 decision — this is the actual enforcement point, not just a UI
    convention. Returns False (and arms nothing) if the user isn't allowed.
    """
    if not getattr(user, "is_superuser", False):
        return False
    redis_conn.setex(_arm_key(user.id), ARM_TTL_SECONDS, "1")
    return True


def is_armed(user) -> bool:
    return redis_conn.get(_arm_key(user.id)) is not None


def disarm(user):
    redis_conn.delete(_arm_key(user.id))


# ---------------------------------------------------------------------------
# The middleware. Written against the real Django middleware shape
# (get_response closure, __call__(request)) so this is drop-in-able, not
# pseudocode — but NOT yet tested against a real Django request object,
# only the fake Request stand-in in demo_middleware.py below.
# ---------------------------------------------------------------------------
class TrackerTriggerMiddleware:
    """
    Add to MIDDLEWARE, after auth middleware (needs request.user resolved)
    and before anything that might call a @traced function.

    One-shot semantics: if armed, this request gets traced AND the flag is
    disarmed immediately — the NEXT request after this one is NOT traced,
    even if this one is still in flight. This is deliberate: "trace my
    next request" should mean exactly one, not "until I remember to turn
    it off".
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        traced_this_request = False

        if user is not None and getattr(user, "is_authenticated", False):
            if is_armed(user):
                disarm(user)  # one-shot: consume the flag before the view runs,
                               # not after — so a crash mid-view can't leave it
                               # armed for a retry to double-fire
                start_trace(transaction_id=f"user{user.id}-{int(time.time())}")
                traced_this_request = True

        response = self.get_response(request)

        # Real version: this is where the completed Trace gets persisted
        # to runtime_events and/or attached to the response for the admin
        # UI to pick up (e.g. a response header with the transaction_id
        # so Peter can immediately open the trace after triggering it).
        # NOT built yet — see notes at the bottom of this file.

        return response
