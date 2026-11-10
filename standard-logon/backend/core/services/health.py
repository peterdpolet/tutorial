"""
Health service: can the application do its job right now?

This is the pattern for the whole series. A service is a plain Python function
that holds the rule and knows nothing about HTTP: no request, no response, no
status codes. The API view calls it today; an HTMX view or a management
command can call the very same function later without copying the rule.
"""
from django.db import DatabaseError, connection


def check_health():
    """Return a dict describing the state of the application.

    The one real check is a trivial query: if the database answers, the
    application can serve requests; if it does not, we report "degraded"
    rather than raising, so the caller decides how to present that.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        database = "ok"
    except DatabaseError:
        database = "unavailable"

    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
    }
