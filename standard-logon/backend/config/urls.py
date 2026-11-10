"""
Top-level URLs. Everything the front end calls lives under /api/.
Later episodes add their own include() lines here.
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("core.urls")),
]
