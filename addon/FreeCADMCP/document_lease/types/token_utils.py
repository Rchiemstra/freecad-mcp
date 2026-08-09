from __future__ import annotations

import hashlib
import hmac
import re

from .lease_model_error import LeaseModelError

TOKEN_FINGERPRINT_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def token_fingerprint(token: str) -> str:
    """Return the only token representation allowed in persistent state."""

    if not isinstance(token, str) or not token:
        raise LeaseModelError("lease token must be a non-empty string")
    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_matches(token: str, fingerprint: str) -> bool:
    """Compare a supplied raw token with a stored SHA-256 fingerprint."""

    if not isinstance(fingerprint, str) or not TOKEN_FINGERPRINT_RE.fullmatch(
        fingerprint
    ):
        return False
    try:
        actual = token_fingerprint(token)
    except LeaseModelError:
        return False
    return hmac.compare_digest(actual, fingerprint)
