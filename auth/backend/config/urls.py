from django.urls import include, path

urlpatterns = [
    path("api/tracker/", include("tracker.urls")),
    path("api/auth/", include("accounts.urls")),
]
