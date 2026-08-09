"""Extracted ``LeaseCredential`` for ARCH002 (workstream 1G)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .constants import _REDACTED
from .protocol_error import ProtocolError
from .validation import (
    _require_exact_keys,
    _require_uuid,
    _validate_token,
)


@dataclass(frozen=True)
class LeaseCredential:
    lease_id: str
    document_session_uuid: str
    generation: int
    token: str = field(repr=False)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> LeaseCredential:
        if not isinstance(payload, Mapping):
            raise ProtocolError(
                "MALFORMED_LEASE_CREDENTIAL", "Lease credential must be an object"
            )
        _require_exact_keys(
            payload,
            required={"lease_id", "document_session_uuid", "generation", "token"},
            context="lease credential",
        )
        generation = payload["generation"]
        if (
            isinstance(generation, bool)
            or not isinstance(generation, int)
            or not 1 <= generation <= (2**63 - 1)
        ):
            raise ProtocolError(
                "INVALID_LEASE_GENERATION",
                "Lease credential generation must be a positive integer",
            )
        return cls(
            lease_id=_require_uuid(payload["lease_id"], "lease_id"),
            document_session_uuid=_require_uuid(
                payload["document_session_uuid"], "document_session_uuid"
            ),
            generation=generation,
            token=_validate_token(payload["token"], "lease token"),
        )

    def redacted_dict(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "document_session_uuid": self.document_session_uuid,
            "generation": self.generation,
            "token": _REDACTED,
        }
