"""
Who may switch tracing on, and who may read the results.

One function answers both questions, so the rule cannot drift apart: if you
may not trace, you may not read traces either. Point the TRACKER_AUTHORISE
setting at your own function to change the rule.

The default is deliberately strict: a logged-in staff user, nobody else. A
trace records real values from a live request, so it is never open to the
public.
"""


def default_authorise(request) -> bool:
    user = getattr(request, "user", None)
    return bool(user is not None and user.is_authenticated and user.is_staff)


# ---------------------------------------------------------------------------
# Tracing requests nobody is logged in for (register, login, password reset)
# ---------------------------------------------------------------------------
# You cannot trace "register" with the default rule: the person registering is
# not a logged-in staff user. This rule opens a narrow, development-only door:
#
#   * settings.DEBUG must be True          (never on a real server)
#   * the request must come from this machine (loopback), unless you turn
#     TRACKER_DEV_LOOPBACK_ONLY off (Docker dev, where the caller is the gateway)
#   * the path must start with a prefix you listed in TRACKER_DEV_ANON_PREFIXES
#     (default: none, so nothing is opened until you choose)
#   * the tracker's own read API is never opened, whatever you list
#
# Logged-in staff are still allowed everywhere, as with the default rule.
# Every other condition (TRACKER_ENABLED, the X-Tracker header) still applies.
# Redaction still applies too: passwords, tokens and emails are blanked before
# anything is stored.

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def dev_authorise(request) -> bool:
    if default_authorise(request):
        return True
    from django.conf import settings

    if not getattr(settings, "DEBUG", False):
        return False
    prefixes = tuple(getattr(settings, "TRACKER_DEV_ANON_PREFIXES", ()) or ())
    path = getattr(request, "path", "") or ""
    if not prefixes or not path.startswith(prefixes):
        return False
    if "/tracker/" in path:  # never expose the trace viewer itself
        return False
    if getattr(settings, "TRACKER_DEV_LOOPBACK_ONLY", True):
        meta = getattr(request, "META", {}) or {}
        if meta.get("REMOTE_ADDR") not in _LOOPBACK:
            return False
    return True
