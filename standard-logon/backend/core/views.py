"""
Views for the core app.

A view only translates: it takes the HTTP request, calls a service, and turns
the result back into an HTTP response. It decides nothing about the business.
"""
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from core.services import health
from tracker.tracker import checkpoint, traced


@require_GET
@traced("Health view")
def health_view(request):
    result = health.check_health()
    # The service says what is true; the view maps that to an HTTP status.
    status_code = 200 if result["status"] == "ok" else 503
    checkpoint("http_status_chosen", status=result["status"], status_code=status_code)
    return JsonResponse(result, status=status_code)
