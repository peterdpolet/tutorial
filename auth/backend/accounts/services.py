"""
Episode 1: Register.

The whole flow, in the order it happens:

    register_view (views.py)          reads the request, turns errors into replies
      -> register                     the one entry point; runs the steps below
           1. clean_email             tidy the address
           2. check_email_free        refuse an address already registered
           3. check_password          refuse a weak password
           4. create_inactive_user    save the user, NOT yet allowed to log in
           5. issue_verification_token  make the secret for the emailed link
           6. send_verification_email   print the email (console, in development)

Every step is @traced and records a checkpoint at each decision, so a trace
reads as a story: what came in, which decision was taken, what went out.

Rules for traced functions here: they sit at module level and take
keyword-only arguments, so the trace shows every value by name.
"""
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email

from tracker.tracker import checkpoint, traced

from .models import EmailToken

User = get_user_model()


class RegistrationError(Exception):
    """A refusal the user can fix. `field` says which input; `messages` why."""

    def __init__(self, field, messages):
        super().__init__(f"{field}: {'; '.join(messages)}")
        self.field = field
        self.messages = list(messages)


@traced("clean_email")
def clean_email(*, email):
    email = (email or "").strip().lower()
    try:
        validate_email(email)
    except ValidationError:
        checkpoint("email_invalid")
        raise RegistrationError("email", ["Enter a valid email address."])
    return email


@traced("check_email_free")
def check_email_free(*, email):
    taken = User.objects.filter(username=email).exists()
    checkpoint("duplicate_check", taken=taken)
    if taken:
        raise RegistrationError("email", ["That email is already registered."])


@traced("check_password")
def check_password(*, email, password):
    try:
        validate_password(password, user=User(username=email, email=email))
    except ValidationError as exc:
        checkpoint("password_refused", reasons=len(exc.messages))
        raise RegistrationError("password", exc.messages)
    checkpoint("password_accepted")


@traced("create_inactive_user")
def create_inactive_user(*, email, password):
    user = User.objects.create_user(username=email, email=email, password=password)
    user.is_active = False  # cannot log in until the emailed link is used
    user.save(update_fields=["is_active"])
    checkpoint("user_created", user_id=user.pk, is_active=user.is_active)
    return user


@traced("issue_verification_token")
def issue_verification_token(*, user):
    token = EmailToken.objects.create(user=user, token=secrets.token_urlsafe(32))
    checkpoint("token_issued", row=token.pk)
    return token


@traced("send_verification_email")
def send_verification_email(*, user, token):
    link = f"{settings.FRONTEND_URL}/verify?token={token.token}"
    send_mail(
        subject="Confirm your email",
        message=f"Welcome! Confirm your email address by opening this link:\n\n{link}\n",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )
    checkpoint("email_sent", to_domain=user.email.split("@")[-1])


@traced("register")
def register(*, email, password):
    email = clean_email(email=email)
    check_email_free(email=email)
    check_password(email=email, password=password)
    user = create_inactive_user(email=email, password=password)
    token = issue_verification_token(user=user)
    send_verification_email(user=user, token=token)
    return user
