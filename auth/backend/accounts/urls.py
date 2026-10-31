from django.urls import path

from . import views

urlpatterns = [
    path("register/", views.register_view, name="auth-register"),
    path("verify/", views.verify_view, name="auth-verify"),
    path("login/", views.login_view, name="auth-login"),
    path("refresh/", views.refresh_view, name="auth-refresh"),
    path("logout/", views.logout_view, name="auth-logout"),
    path("me/", views.me_view, name="auth-me"),
]
