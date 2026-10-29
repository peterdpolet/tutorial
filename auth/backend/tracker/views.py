"""
A small read API for the browser viewer (plain Django, no DRF needed):

  GET runs/          the most recent runs, newest first (summaries only)
  GET runs/<uuid>/   one run with its full call tree

Same rule as for switching tracing on: if TRACKER_AUTHORISE says no, the
answer is 403. Traces hold real values from live requests.
"""
from django.http import Http404, JsonResponse

from .middleware import authorise
from .models import TraceRun
from .persist import build_tree, run_summary


def _guard(request):
    if not authorise(request):
        return JsonResponse({"detail": "Not authorised."}, status=403)
    return None


def run_list(request):
    denied = _guard(request)
    if denied:
        return denied
    runs = TraceRun.objects.all()[:50]
    return JsonResponse({"results": [run_summary(r) for r in runs]})


def run_detail(request, run_id):
    denied = _guard(request)
    if denied:
        return denied
    try:
        run = TraceRun.objects.get(pk=run_id)
    except TraceRun.DoesNotExist:
        raise Http404("No such trace.")
    return JsonResponse(build_tree(run))


# --- static code graph -----------------------------------------------------

from . import graph as graph_store  # noqa: E402


def graph_projects(request):
    denied = _guard(request)
    if denied:
        return denied
    from .models import CodeEntity
    names = sorted(CodeEntity.objects.values_list("project", flat=True).distinct())
    return JsonResponse({"projects": names})


def graph_detail(request, project):
    denied = _guard(request)
    if denied:
        return denied
    data = graph_store.graph(project)
    if not data["entities"]:
        raise Http404("No graph loaded for that project.")
    return JsonResponse(data)


def graph_flow(request, project):
    denied = _guard(request)
    if denied:
        return denied
    start = request.GET.get("start", "")
    data = graph_store.flow(project, start)
    if data is None:
        raise Http404("Unknown start entity.")
    return JsonResponse(data)


def graph_match(request, project):
    denied = _guard(request)
    if denied:
        return denied
    found = graph_store.match_request(project, request.GET.get("method", "GET"), request.GET.get("path", ""))
    if found is None:
        raise Http404("No route matches.")
    return JsonResponse(found)
