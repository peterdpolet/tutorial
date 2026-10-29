from django.apps import AppConfig


class TrackerConfig(AppConfig):
    """
    The Django side of the tracker: storage, the middleware that switches
    tracing on, and a small read API.

    The capture mechanism itself (tracker.py, redaction.py) does not import
    Django and does not import anything in this file's neighbours, so it can
    still be used and tested without a database.
    """
    name = "tracker"
    default_auto_field = "django.db.models.BigAutoField"
