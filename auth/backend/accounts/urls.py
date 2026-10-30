from django.urls import path

from . import views

urlpatterns = [
    path("register/", views.register_view, name="auth-register"),
    path("verify/", views.verify_view, name="auth-verify"),
    path("login/", views.login_view, name="auth-login"),
    path("me/", views.me_view, name="auth-me"),
]
