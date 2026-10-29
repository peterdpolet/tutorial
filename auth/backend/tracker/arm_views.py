"""
Tracker II — the toggle endpoint. Wires the already-proven arm_next_request/
is_armed/disarm functions (trigger.py) into a real DRF view.

Superuser check happens TWICE, deliberately — once here at the view level
(IsAdminUser, DRF's built-in permission class that checks is_staff... see
note below, this needs is_superuser specifically) and once again inside
arm_next_request() itself. This is NOT redundant: the view-level check
stops an unauthorized request before it does anything at all (returns
403, no side effect attempted); the function-level check is what actually
protects the mechanism even if some OTHER code path ever calls
arm_next_request() directly, bypassing this view entirely. Belt and
braces — the same principle as the three-layer redaction system.

IMPORTANT: DRF's built-in IsAdminUser checks user.is_staff, NOT
user.is_superuser — those are different flags in Django (a staff user
can access /admin/ without being a superuser). Given the whole point of
this feature is "superuser only", a CUSTOM permission class is used
below rather than reaching for IsAdminUser and assuming it means what
its name suggests — a real, easy mistake this file deliberately avoids
rather than glossing over.
"""
from rest_framework.views import APIView
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework import status

from .trigger import arm_next_request, is_armed, disarm


class IsSuperuser(BasePermission):
    """Custom, because DRF's IsAdminUser checks is_staff, not
    is_superuser — see module docstring. Named explicitly so the intent
    is unambiguous at the view's permission_classes line, not buried in
    a comment someone has to go find."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


class TrackerArmView(APIView):
    """
    POST /api/tracker/arm/    -> arm capture for this user's next request
    GET  /api/tracker/arm/    -> check current armed status
    DELETE /api/tracker/arm/  -> manually disarm (e.g. "changed my mind")

    All three require superuser — enforced by permission_classes AND,
    for POST, again inside arm_next_request() itself.
    """
    permission_classes = [IsSuperuser]

    def get(self, request):
        return Response({"armed": is_armed(request.user)})

    def post(self, request):
        armed = arm_next_request(request.user)
        if not armed:
            # This shouldn't be reachable given permission_classes already
            # blocked non-superusers, but arm_next_request()'s own check
            # is what actually matters — if it ever returns False here,
            # something is inconsistent between the two checks, worth
            # knowing about rather than silently returning success.
            return Response(
                {"armed": False, "error": "arm_next_request() refused — check superuser status"},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response({"armed": True})

    def delete(self, request):
        disarm(request.user)
        return Response({"armed": False})


# ---------------------------------------------------------------------------
# urls.py wiring (not a separate file for this small a change — shown here
# as the literal snippet to add):
#
# from tracker.views import TrackerArmView
# urlpatterns += [
#     path('api/tracker/arm/', TrackerArmView.as_view(), name='tracker-arm'),
# ]
# ---------------------------------------------------------------------------
