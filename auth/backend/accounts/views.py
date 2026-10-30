"""
The HTTP edge of Register: read the JSON, call the service, shape the reply.

  201  {"detail": "..."}                 registered; check your email
  400  {"errors": {"email": [...]}}      something the user can fix
  400  {"detail": "..."}                 the request itself was not usable

Episode 2 adds verify_view: the same shape for the emailed link.
Episode 3 adds login_view (tokens, or a refusal with its own status) and me_view.
"""
import json

from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from tracker.tracker import traced

from .login import LoginError, authenticate_access, login
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
