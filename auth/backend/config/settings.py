"""
Settings for the auth tutorial.

DEVELOPMENT ONLY: a throw-away secret key, SQLite, DEBUG on, and emails printed
to the terminal. None of this is suitable for a real server; the deployment
episodes replace it step by step.
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "tutorial-only-not-a-secret"
DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "tracker",     # copied in from spadetrack (see the episode notes)
    "accounts",
]

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # After authentication, so a request's user is known. It traces a request
    # only when it asks to AND the policy below agrees.
    "tracker.middleware.TrackerMiddleware",
]

ROOT_URLCONF = "config.urls"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
TIME_ZONE = "UTC"
USE_TZ = True

# Django's own password rules. A weak password is refused with these messages.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Password hashing is deliberately slow, which makes the login tests crawl.
# While running the tests only, use a fast (insecure) hasher.
import sys
if "test" in sys.argv:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Emails are printed to the terminal, never sent. (The test runner swaps in an
# in-memory backend automatically.)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "noreply@example.com"

# Where the link in the verification email points: the Vue dev server.
FRONTEND_URL = "http://localhost:5273"

# How long the emailed confirmation link works, in hours.
EMAIL_TOKEN_LIFETIME_HOURS = 24

# Login (episode 3). Invented numbers; a real site chooses its own.
LOGIN_MAX_FAILURES = 5        # wrong passwords in a row before the address locks
LOGIN_LOCK_MINUTES = 15       # how long the lock lasts
ACCESS_TOKEN_SECONDS = 900    # the short-lived token: 15 minutes
REFRESH_TOKEN_DAYS = 14       # the long-lived token (episode 4 spends it)

# --- Tracker -------------------------------------------------------------
# Off unless True. A request is traced only if it also sends  X-Tracker: 1
# and the policy below says yes.
TRACKER_ENABLED = DEBUG
# Register, login and reset are used by people who are not logged in, so the
# default rule (logged-in staff only) would never trace them. This development
# rule allows the listed paths, only while DEBUG is on and only from this
# machine. It never opens the trace viewer itself.
TRACKER_AUTHORISE = "tracker.policy.dev_authorise"
TRACKER_DEV_ANON_PREFIXES = ["/api/auth/"]
# The trace viewer (Flow view, VS Code extension) normally answers logged-in
# staff only. Logging in (episode 3) gives people an access token, but the
# tracker only recognises Django staff logins, not that token. So this stays,
# reading from this machine while DEBUG is on, until the tracker learns to read
# the token. Never enable it on a real server.
TRACKER_DEV_ALLOW_VIEWER = True
