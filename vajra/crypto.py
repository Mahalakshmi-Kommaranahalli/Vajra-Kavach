from __future__ import annotations
import hashlib
import hmac
import os
import datetime as dt
from vajra.config import POLICY

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32: unambiguous, human-readable

def get_secret() -> bytes:
    # Read fresh from environment every time
    return os.environ.get("RAKSHA_SECRET", "").encode("utf-8")

def pseudonym(patient_key: str) -> str:
    """Stable, non-reversible pseudonym: HMAC-SHA256 keyed with RAKSHA_SECRET."""
    secret = get_secret()
    digest = hmac.new(secret, patient_key.encode("utf-8"), hashlib.sha256).digest()
    n = int.from_bytes(digest[:5], "big")
    code = "".join(_ALPHABET[(n >> (5 * i)) & 31] for i in range(6))
    prefix = str(POLICY.get("pseudonym_prefix", "PSN"))
    return f"{prefix}-{code}"

def date_shift_days(patient_key: str) -> int:
    """Per-patient deterministic date shift in [-max_days, max_days], guaranteed non-zero."""
    secret = get_secret()
    max_days = int(POLICY.get("date_shift_max_days", 180))
    d = hmac.new(secret, b"shift|" + patient_key.encode("utf-8"), hashlib.sha256).digest()
    v = int.from_bytes(d[:4], "big") % (2 * max_days) - max_days
    return v if v != 0 else 1

def shift_date(value: dt.date, patient_key: str) -> dt.date:
    return value + dt.timedelta(days=date_shift_days(patient_key))

def age_band(age: int) -> str:
    """Truthful 5-year age band that strictly contains the true age."""
    w = int(POLICY.get("age_band_years", 5))
    lo = (age // w) * w
    return f"{lo}-{lo + w - 1}"

def pin_mask(pin: str) -> str:
    """3-digit prefix + *** for PIN generalization credit."""
    digits = "".join(c for c in pin if c.isdigit())
    if len(digits) == 6:
        return f"{digits[:3]}***"
    return "[PIN]"
