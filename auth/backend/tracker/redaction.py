"""
Tracker II — redaction policy.

Decision (24 Sep): name-based blocklist AND type/pattern-sniffing, not
name-only. Rationale: a checkpoint like
    checkpoint("customer_lookup", contact=customer.email)
uses a kwarg named 'contact', not 'email' — a name-only check would miss
it. Pattern-sniffing the VALUE itself (does this string look like an
email, a card number, a UK NI number...) catches that case even when the
developer didn't think to name the kwarg something obviously sensitive.

This is a genuine defence-in-depth pair, not redundant: name-matching
catches things whose VALUE wouldn't look obviously sensitive on its own
(e.g. a field named 'ssn' holding a value that's just digits, which a
naive pattern check might not flag confidently); pattern-sniffing catches
things whose NAME wouldn't tip you off. Neither alone is enough.

Explicitly NOT solved here: this cannot catch every possible sensitive
value (e.g. a customer's name in a field called 'contact_person' — no
name signal, no reliable pattern to sniff for "this looks like a human
name"). Flagged honestly at the bottom, not glossed over.
"""
import re
from collections.abc import Mapping


# ---------------------------------------------------------------------------
# Name-based blocklist. Matched against kwarg names AND Django model field
# names (case-insensitive substring match, so 'user_email' and 'EmailAddr'
# both match 'email').
# ---------------------------------------------------------------------------
SENSITIVE_NAME_FRAGMENTS = [
    "password", "passwd", "pwd",
    "token", "secret", "api_key", "apikey",
    "email",
    "ssn", "social_security",
    "credit_card", "card_number", "cvv", "cvc",
    "bank_account", "iban", "sort_code",
    "certificate_number", "certification_number",  # e.g. gemstone lab certificate numbers
    "auth", "session_key", "csrf",
]


def _name_is_sensitive(name: str) -> bool:
    name_lower = name.lower()
    return any(fragment in name_lower for fragment in SENSITIVE_NAME_FRAGMENTS)


# ---------------------------------------------------------------------------
# Pattern-sniffing. Each check is deliberately conservative (favour missing
# an edge case over flagging so much normal data that redaction becomes
# noise) — these are the highest-confidence, lowest-false-positive shapes.
# ---------------------------------------------------------------------------
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CARD_RE = re.compile(r"^\d{13,19}$")  # after stripping spaces/dashes
_UK_NI_RE = re.compile(r"^[A-CEGHJ-PR-TW-Z]{2}\d{6}[A-D]$", re.IGNORECASE)
_PHONE_RE = re.compile(r"^\+?\d[\d\s\-\(\)]{7,}\d$")  # loose — flagged as broad below


def _value_looks_sensitive(value_str: str) -> str | None:
    """Returns a short reason string if the VALUE itself looks sensitive,
    else None. Only called on plain strings — never on Decimal, int, model
    tags etc, which are structurally not going to match these shapes."""
    stripped = value_str.strip()
    if _EMAIL_RE.match(stripped):
        return "looks like an email address"

    digits_only = re.sub(r"[\s\-]", "", stripped)
    if _CARD_RE.match(digits_only):
        return "looks like a card/account number"

    if _UK_NI_RE.match(stripped):
        return "looks like a UK National Insurance number"

    if _PHONE_RE.match(stripped) and len(re.sub(r"\D", "", stripped)) >= 9:
        return "looks like a phone number"

    return None


REDACTED = "[REDACTED]"


def redact_if_sensitive(name: str, value_str: str) -> str:
    """
    The actual policy entry point. name is the kwarg/field name (may be
    empty string if there's no name context, e.g. a positional arg);
    value_str is the already-str()'d value (what safe_repr would otherwise
    return as-is).

    Returns either the original value_str unchanged, or a REDACTED marker
    that still tells you WHY it was redacted (useful for a developer
    reviewing a trace to understand the tool is working correctly, not
    silently eating data) — without leaking the value itself.
    """
    if name and _name_is_sensitive(name):
        return f"{REDACTED} (field name matched sensitive pattern)"

    reason = _value_looks_sensitive(value_str)
    if reason:
        return f"{REDACTED} ({reason})"

    return value_str


# ---------------------------------------------------------------------------
# Inline redaction, for free text (e.g. exception messages).
#
# redact_if_sensitive() above only fires when a WHOLE value is an email,
# phone number etc (its patterns are anchored with ^...$). Free text such as
#     "no such customer: jane@example.com"
# is a sentence with a sensitive piece INSIDE it, so the anchored checks never
# match. redact_text() finds the piece anywhere in the text and replaces just
# that piece, so the rest of the message stays readable for debugging.
#
# Same philosophy as above: conservative shapes, and the same honest gaps
# (names and addresses are NOT caught).
# ---------------------------------------------------------------------------
_INLINE_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_INLINE_CARD_RE = re.compile(r"(?<![\w.])(?:\d[ \-]?){12,18}\d(?![\w])")
_INLINE_NI_RE = re.compile(
    r"\b[A-CEGHJ-PR-TW-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b", re.IGNORECASE
)
# The (?!\d{4}-\d{2}-\d{2}) lookahead stops ISO dates ("2026-10-28 12:24") being
# mistaken for phone numbers: timestamps are everywhere in exception messages.
_INLINE_PHONE_RE = re.compile(
    r"(?<![\w.])(?!\d{4}-\d{2}-\d{2})\+?\d[\d\s\-()]{7,}\d(?![\w])"
)


# A secret carried in a link: https://site/reset?token=abc  or  ...?t=abc.
# The VARIABLE holding the link may be called anything ("reset_link"), so the
# name check never fires; the query parameter's own name is what gives it away.
_URL_SECRET_RE = re.compile(
    r"([?&;](?:t|token|key|api_key|apikey|secret|sig|signature|code|otp|"
    r"reset|auth|access_token|refresh_token|session|sid|password|pwd)=)[^&\s'\"<>#]+",
    re.IGNORECASE,
)


def _marker(kind: str) -> str:
    return f"{REDACTED} ({kind})"


def _redact_phone_match(match: "re.Match") -> str:
    # Same 9-digit floor as _value_looks_sensitive(), so short numbers such
    # as "order 12345" are left alone.
    if len(re.sub(r"\D", "", match.group(0))) >= 9:
        return _marker("phone number")
    return match.group(0)


def redact_text(text: str) -> str:
    """Replace any email / card number / NI number / phone number found INSIDE
    free text with a marker saying what was removed (never the value itself).
    Order matters: card numbers are checked before phone numbers, because a
    13-19 digit run would otherwise be mis-labelled as a phone number."""
    text = _URL_SECRET_RE.sub(lambda m: m.group(1) + _marker("secret in link"), text)
    text = _INLINE_EMAIL_RE.sub(_marker("email address"), text)
    text = _INLINE_CARD_RE.sub(_marker("card/account number"), text)
    text = _INLINE_NI_RE.sub(_marker("UK National Insurance number"), text)
    text = _INLINE_PHONE_RE.sub(_redact_phone_match, text)
    return text


# ---------------------------------------------------------------------------
# Sensitive KEYS inside captured containers.
#
# A value like "hunter2" has no shape that gives it away; only the dict key it
# sits under ("password") does. The argument-name check cannot see keys inside
# a dict passed as ONE argument (e.g. a request payload), so
# scrub_sensitive_keys() applies the same name blocklist to every dict key.
#
# It returns a COPY: the program's real data is never modified. Limits keep
# it cheap and safe on large or odd structures: nesting depth, items per
# container, and self-referencing structures are all bounded.
#
# Known gap: only dict KEYS are inspected. A list of pairs such as
# [("api_key", "sk_live_...")] is not recognised as key/value data.
# ---------------------------------------------------------------------------
_MAX_SCRUB_DEPTH = 6
_MAX_SCRUB_ITEMS = 100


def scrub_sensitive_keys(value, _depth: int = 0, _path: frozenset = frozenset()):
    if not isinstance(value, (Mapping, list, tuple)):
        return value
    if _depth >= _MAX_SCRUB_DEPTH or id(value) in _path:
        return "<nested too deeply, or refers to itself>"
    _path = _path | {id(value)}

    if isinstance(value, Mapping):
        out = {}
        for i, (key, item) in enumerate(value.items()):
            if i >= _MAX_SCRUB_ITEMS:
                out["..."] = f"(+{len(value) - i} more)"
                break
            if isinstance(key, str) and _name_is_sensitive(key):
                out[key] = f"{REDACTED} (field name matched sensitive pattern)"
            else:
                out[key] = scrub_sensitive_keys(item, _depth + 1, _path)
        return out

    items = []
    for i, item in enumerate(value):
        if i >= _MAX_SCRUB_ITEMS:
            items.append(f"(+{len(value) - i} more)")
            break
        items.append(scrub_sensitive_keys(item, _depth + 1, _path))
    return tuple(items) if isinstance(value, tuple) else items


# ---------------------------------------------------------------------------
# Honest gaps, not solved here:
#
# 1. Human names (customer/supplier names) have no reliable name-fragment
#    OR pattern signal — 'bp_name', 'customer', 'description' could hold a
#    person's name or could hold "0.52ct Diamond", no way to tell from the
#    field name or the string shape alone. NOT redacted by this policy.
#    Real mitigation available: emillar_v2's own field-level knowledge
#    (e.g. specifically flag BusinessPartner.bp_name as sensitive by
#    Django field, not by string pattern) — a schema-aware layer, not a
#    generic one. Not built here.
#
# 2. Physical addresses — same problem as names, no reliable signal.
#
# 3. The phone regex above is broad enough to occasionally false-positive
#    on things that aren't phone numbers (e.g. a long reference code that's
#    mostly digits) — flagged as a real tuning risk, not swept under the
#    rug. Given the cost of over-redacting is much lower than under-
#    redacting, this is an acceptable v1 trade, but worth knowing about.
# ---------------------------------------------------------------------------
