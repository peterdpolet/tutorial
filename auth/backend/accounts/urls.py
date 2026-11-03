from django.urls import path

from . import views

urlpatterns = [
    path("register/", views.register_view, name="auth-register"),
    path("verify/", views.verify_view, name="auth-verify"),
    path("login/", views.login_view, name="auth-login"),
    path("refresh/", views.refresh_view, name="auth-refresh"),
    path("logout/", views.logout_view, name="auth-logout"),
    path("forgot/", views.forgot_view, name="auth-forgot"),
    path("reset/", views.reset_view, name="auth-reset"),
    path("2fa/setup/", views.two_factor_setup_view, name="auth-2fa-setup"),
    path("2fa/confirm/", views.two_factor_confirm_view, name="auth-2fa-confirm"),
    path("2fa/login/", views.two_factor_login_view, name="auth-2fa-login"),
    path("me/", views.me_view, name="auth-me"),
]
