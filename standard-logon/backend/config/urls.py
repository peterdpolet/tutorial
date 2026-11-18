"""
Top-level URLs. Everything the front end calls lives under /api/.
Later episodes add their own include() lines here.
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("core.urls")),
    # spadetrack's own endpoints (the trace viewer reads these). They answer
    # only when TRACKER_ENABLED is on and the policy allows the caller.
    path("api/tracker/", include("tracker.urls")),
]
