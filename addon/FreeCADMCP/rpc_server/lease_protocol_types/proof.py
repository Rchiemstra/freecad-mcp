"""HMAC proof helpers for authenticated handshake payloads."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from typing import Any

from .constants import _PROOF_RE, HMAC_ALGORITHM
from .lease_protocol_error import LeaseProtocolError
from .validation import _validate_secret, canonical_json_bytes


def _proof(secret: bytes, domain: bytes, payload: Mapping[str, Any]) -> str:
    digest = hmac.new(
        _validate_secret(secret), domain + canonical_json_bytes(dict(payload)), hashlib.sha256
    ).hexdigest()
    return f"{HMAC_ALGORITHM}:{digest}"


def _verify_proof(
    secret: bytes,
    domain: bytes,
    payload_without_proof: Mapping[str, Any],
    presented: Any,
) -> None:
    if not isinstance(presented, str) or not _PROOF_RE.fullmatch(presented):
        raise LeaseProtocolError(
            "AUTHENTICATION_FAILED", "Handshake authentication failed"
        )
    expected = _proof(secret, domain, payload_without_proof)
    if not hmac.compare_digest(expected, presented):
        raise LeaseProtocolError(
            "AUTHENTICATION_FAILED", "Handshake authentication failed"
        )
