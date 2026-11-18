from django.urls import path

from . import views

urlpatterns = [
    path("runs/", views.run_list, name="tracker-run-list"),
    path("runs/<uuid:run_id>/", views.run_detail, name="tracker-run-detail"),
    path("graph/", views.graph_projects, name="tracker-graph-projects"),
    path("graph/<str:project>/", views.graph_detail, name="tracker-graph"),
    path("graph/<str:project>/flow/", views.graph_flow, name="tracker-graph-flow"),
    path("graph/<str:project>/match/", views.graph_match, name="tracker-graph-match"),
]
