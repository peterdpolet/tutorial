from django.urls import path

from core import views

app_name = "core"

urlpatterns = [
    path("health/", views.health_view, name="health"),
]
