"""
Switches tracing on for ONE request, when (and only when) all of these hold:

  1. settings.TRACKER_ENABLED is True            (default False: off everywhere)
  2. settings.TRACKER_AUTHORISE(request) is True  (default: logged-in staff)
  3. the request ASKS to be traced, in either of two ways:
       a. it carries the header  X-Tracker: 1      (a per-request ask), or
       b. its user has ARMED their next request    (trigger.py: a superuser
          armed it from the toggle endpoint; the arm is one-shot and expires)

If any condition fails the request runs untraced, exactly as if this
middleware were not installed. If the authorise function itself errors, that
counts as "no" (fail closed). An armed flag is only consumed by a request
that passed every other check.

Place it AFTER AuthenticationMiddleware so request.user exists.

When a request is traced the response gains an  X-Tracker-Run  header holding
the id of the saved run. A request in which no traced code ran saves nothing
(so reading traces never fills the tables with empty runs). A problem while SAVING a trace is logged and
swallowed: tracing must never break the request it is observing.
"""
import logging
import time

from django.conf import settings
from django.utils.module_loading import import_string

from .persist import save_trace
from .trigger import disarm, is_armed
from .tracker import _current_trace, start_trace

logger = logging.getLogger("tracker")

REQUEST_HEADER = "X-Tracker"
RESPONSE_HEADER = "X-Tracker-Run"


def authorise(request) -> bool:
    path = getattr(settings, "TRACKER_AUTHORISE", "tracker.policy.default_authorise")
    try:
        return bool(import_string(path)(request))
    except Exception:
        logger.exception("tracker: authorise check failed; treating as not authorised")
        return False


class TrackerMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def _should_trace(self, request) -> bool:
        if not getattr(settings, "TRACKER_ENABLED", False):
            return False
        if not authorise(request):
            return False
        if request.headers.get(REQUEST_HEADER) == "1":
            return True
        return self._consume_arm(request)

    @staticmethod
    def _consume_arm(request) -> bool:
        """One-shot: if this user armed their next request, use it up now,
        BEFORE the view runs, so a crash mid-view cannot leave it armed for a
        retry to fire twice."""
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return False
        try:
            if is_armed(user):
                disarm(user)
                return True
        except Exception:
            logger.exception("tracker: could not check the armed flag")
        return False

    def __call__(self, request):
        if not self._should_trace(request):
            return self.get_response(request)

        trace = start_trace()
        t0 = time.perf_counter()
        try:
            response = self.get_response(request)
        finally:
            _current_trace.set(None)  # tracing ends with the request, whatever happens
        duration_ms = (time.perf_counter() - t0) * 1000

        if not trace.root_calls:
            return response  # nothing traced ran (e.g. the viewer's own requests): nothing to save

        try:
            user = getattr(request, "user", None)
            run = save_trace(
                trace,
                method=request.method,
                path=request.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                user_id=getattr(user, "pk", None) if getattr(user, "is_authenticated", False) else None,
            )
            response[RESPONSE_HEADER] = str(run.pk)
        except Exception:
            logger.exception("tracker: could not save trace")
        return response
