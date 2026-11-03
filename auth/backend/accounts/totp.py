"""
One-time codes, built by hand from the standard (RFC 6238, TOTP).

No library: the whole recipe is a dozen lines, and seeing it is what makes the
flow understandable.

  secret   20 random bytes, shown to the person as 32 letters and digits
           (base32), which they type into an authenticator app once.
  step     the number of 30-second periods since 1 January 1970.
  code     HMAC-SHA1 of the step, keyed with the secret, cut down to six digits.

The phone and the server both know the secret and the clock, so both compute
the same six digits for the same 30 seconds, and nothing travels between them.
Clocks drift a little, so the server also accepts the step before and after.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

STEP_SECONDS = 30
DIGITS = 6
WINDOW = 1          # accept this many steps either side of "now"


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode()


def current_step(now=None):
    return int((time.time() if now is None else now) // STEP_SECONDS)


def code_for(secret, step, digits=DIGITS):
    """The code for one step. Same recipe as HOTP (RFC 4226), with the step as the counter."""
    mac = hmac.new(base64.b32decode(secret, casefold=True), struct.pack(">Q", step), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F                                   # "dynamic truncation": pick 4 bytes
    value = struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10 ** digits).zfill(digits)


def looks_like_a_code(text):
    return len(text) == DIGITS and text.isdigit()


def matching_step(secret, text, *, after_step, now=None):
    """
    The step whose code equals `text`, or None.

    Looks one step either side of now. Only steps AFTER `after_step` count: that
    is what stops a code being used twice, even inside its 30 seconds.
    """
    text = text.strip().replace(" ", "")
    if not looks_like_a_code(text):
        return None
    here = current_step(now)
    found = None
    for step in range(here - WINDOW, here + WINDOW + 1):
        same = hmac.compare_digest(code_for(secret, step), text)     # constant time
        if same and step > after_step:
            found = step
    return found


def provisioning_uri(secret, email, issuer):
    """The address an authenticator app reads from a QR code. Typing the secret in by hand works too."""
    label = quote(f"{issuer}:{email}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}&digits={DIGITS}&period={STEP_SECONDS}"
