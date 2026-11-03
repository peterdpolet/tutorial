"""
The HTTP edge of Register: read the JSON, call the service, shape the reply.

  201  {"detail": "..."}                 registered; check your email
  400  {"errors": {"email": [...]}}      something the user can fix
  400  {"detail": "..."}                 the request itself was not usable

Episode 2 adds verify_view: the same shape for the emailed link.
Episode 3 adds login_view (tokens, or a refusal with its own status) and me_view.
Episode 4 adds refresh_view: a refresh token in, a new pair out (or a 401).
Episode 5 adds logout_view: a refresh token in, that login ended, always a 200.
Episode 6 adds forgot_view (an email in, always the same 200) and reset_view
(a link token and a new password in, 200 or a 400 the person can fix).
Episode 7 adds two_factor_setup_view and two_factor_confirm_view (logged in: turn
two-factor on) and two_factor_login_view (an mfa_token and a code in, tokens out).
"""
import json

from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from tracker.tracker import traced

from .login import LoginError, authenticate_access, login
from .logout import logout
from .refresh import refresh
from .reset import ResetError, request_reset, reset_password
from .twofactor import complete_login, confirm_two_factor, start_setup
from .services import RegistrationError, register
from .verify import VerificationError, verify_email


@require_POST
@traced("register_view")
def register_view(request):
    try:
        body = json.loads(request.body or b"{}")
        if not isinstance(body, dict):
            raise ValueError
    except ValueError:
        return JsonResponse({"detail": "Send a JSON object."}, status=400)

    errors = {}
    for field in ("email", "password"):
        if not isinstance(body.get(field), str) or not body[field].strip():
            errors[field] = ["This field is required."]
    if errors:
        return JsonResponse({"errors": errors}, status=400)

    try:
        register(email=body["email"], password=body["password"])
    except RegistrationError as exc:
        return JsonResponse({"errors": {exc.field: exc.messages}}, status=400)

    return JsonResponse({"detail": "Registered. Check your email to confirm your address."}, status=201)


@require_POST
@traced("verify_view")
def verify_view(request):
    try:
        body = json.loads(request.body or b"{}")
        if not isinstance(body, dict):
            raise ValueError
    except ValueError:
        return JsonResponse({"detail": "Send a JSON object."}, status=400)

    token = body.get("token")
    if not isinstance(token, str) or not token.strip():
        return JsonResponse({"errors": {"token": ["This field is required."]}}, status=400)

    try:
        verify_email(token=token.strip())
    except VerificationError as exc:
        return JsonResponse({"errors": {"token": exc.messages}}, status=400)

    return JsonResponse({"detail": "Email confirmed. Your account is now active."})


@require_POST
@traced("login_view")
def login_view(request):
    try:
        body = json.loads(request.body or b"{}")
        if not isinstance(body, dict):
            raise ValueError
    except ValueError:
        return JsonResponse({"detail": "Send a JSON object."}, status=400)

    errors = {}
    for field in ("email", "password"):
        if not isinstance(body.get(field), str) or not body[field].strip():
            errors[field] = ["This field is required."]
    if errors:
        return JsonResponse({"errors": errors}, status=400)

    try:
        tokens = login(email=body["email"], password=body["password"])
    except LoginError as exc:
        return JsonResponse({"detail": exc.detail}, status=exc.status)

    return JsonResponse(tokens)


@require_GET
@traced("me_view")
def me_view(request):
    header = request.META.get("HTTP_AUTHORIZATION", "")
    scheme, _, access_token = header.partition(" ")
    if scheme != "Bearer" or not access_token.strip():
        return JsonResponse({"detail": "Not logged in."}, status=401)
    try:
        user = authenticate_access(access_token=access_token.strip())
    except LoginError as exc:
        return JsonResponse({"detail": exc.detail}, status=exc.status)
    return JsonResponse({"email": user.username})


@require_POST
@traced("refresh_view")
def refresh_view(request):
    try:
        body = json.loads(request.body or b"{}")
        if not isinstance(body, dict):
            raise ValueError
    except ValueError:
        return JsonResponse({"detail": "Send a JSON object."}, status=400)

    refresh_token = body.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token.strip():
        return JsonResponse({"errors": {"refresh_token": ["This field is required."]}}, status=400)

    try:
        tokens = refresh(refresh_token=refresh_token.strip())
    except LoginError as exc:
        return JsonResponse({"detail": exc.detail}, status=exc.status)

    return JsonResponse(tokens)


@require_POST
@traced("logout_view")
def logout_view(request):
    try:
        body = json.loads(request.body or b"{}")
        if not isinstance(body, dict):
            raise ValueError
    except ValueError:
        return JsonResponse({"detail": "Send a JSON object."}, status=400)

    refresh_token = body.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token.strip():
        return JsonResponse({"errors": {"refresh_token": ["This field is required."]}}, status=400)

    logout(refresh_token=refresh_token.strip(), everywhere=body.get("everywhere") is True)
    return JsonResponse({"detail": "Logged out."})


FORGOT_REPLY = "If that address has an account, we have emailed a link to reset its password."


@require_POST
@traced("forgot_view")
def forgot_view(request):
    try:
        body = json.loads(request.body or b"{}")
        if not isinstance(body, dict):
            raise ValueError
    except ValueError:
        return JsonResponse({"detail": "Send a JSON object."}, status=400)

    email = body.get("email")
    if not isinstance(email, str) or not email.strip():
        return JsonResponse({"errors": {"email": ["This field is required."]}}, status=400)

    request_reset(email=email)
    return JsonResponse({"detail": FORGOT_REPLY})      # the same words whether or not there was an account


@require_POST
@traced("reset_view")
def reset_view(request):
    try:
        body = json.loads(request.body or b"{}")
        if not isinstance(body, dict):
            raise ValueError
    except ValueError:
        return JsonResponse({"detail": "Send a JSON object."}, status=400)

    errors = {}
    for field in ("token", "password"):
        if not isinstance(body.get(field), str) or not body[field].strip():
            errors[field] = ["This field is required."]
    if errors:
        return JsonResponse({"errors": errors}, status=400)

    try:
        reset_password(token=body["token"].strip(), password=body["password"])
    except ResetError as exc:
        return JsonResponse({"errors": {exc.field: exc.messages}}, status=400)

    return JsonResponse({"detail": "Password changed. Log in with your new password."})


def _json_body(request):
    """The request body as a dict, or None when it is not a JSON object."""
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


def _logged_in_user(request):
    header = request.META.get("HTTP_AUTHORIZATION", "")
    scheme, _, access_token = header.partition(" ")
    if scheme != "Bearer" or not access_token.strip():
        raise LoginError(401, "Not logged in.")
    return authenticate_access(access_token=access_token.strip())


@require_POST
@traced("two_factor_setup_view")
def two_factor_setup_view(request):
    try:
        user = _logged_in_user(request)
        setup = start_setup(user=user)
    except LoginError as exc:
        return JsonResponse({"detail": exc.detail}, status=exc.status)
    return JsonResponse(setup)


@require_POST
@traced("two_factor_confirm_view")
def two_factor_confirm_view(request):
    body = _json_body(request)
    if body is None:
        return JsonResponse({"detail": "Send a JSON object."}, status=400)
    try:
        user = _logged_in_user(request)
        if not isinstance(body.get("code"), str) or not body["code"].strip():
            return JsonResponse({"errors": {"code": ["This field is required."]}}, status=400)
        result = confirm_two_factor(user=user, otp_code=body["code"])
    except LoginError as exc:
        return JsonResponse({"detail": exc.detail}, status=exc.status)
    return JsonResponse(result)         # {"recovery_codes": [...]}


@require_POST
@traced("two_factor_login_view")
def two_factor_login_view(request):
    body = _json_body(request)
    if body is None:
        return JsonResponse({"detail": "Send a JSON object."}, status=400)
    errors = {}
    for field in ("mfa_token", "code"):
        if not isinstance(body.get(field), str) or not body[field].strip():
            errors[field] = ["This field is required."]
    if errors:
        return JsonResponse({"errors": errors}, status=400)
    try:
        tokens = complete_login(mfa_token=body["mfa_token"].strip(), otp_code=body["code"])
    except LoginError as exc:
        return JsonResponse({"detail": exc.detail}, status=exc.status)
    return JsonResponse(tokens)
