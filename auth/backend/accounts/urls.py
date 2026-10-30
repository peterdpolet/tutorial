from django.urls import path

from . import views

urlpatterns = [
    path("register/", views.register_view, name="auth-register"),
    path("verify/", views.verify_view, name="auth-verify"),
]
