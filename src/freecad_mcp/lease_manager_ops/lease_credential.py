"""LeaseCredential — extracted from lease_manager."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class LeaseCredential:
    """Secret credential for exactly one document lease generation."""

    lease_id: str
    document_session_uuid: str
    generation: int
    token: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.lease_id:
            raise ValueError("lease_id must not be empty")
        if not self.document_session_uuid:
            raise ValueError("document_session_uuid must not be empty")
        if not isinstance(self.generation, int) or isinstance(self.generation, bool):
            raise TypeError("generation must be an integer")
        if self.generation < 0:
            raise ValueError("generation must be non-negative")
        if not self.token:
            raise ValueError("token must not be empty")

    @property
    def token_fingerprint(self) -> str:
        """A diagnostic/fencing digest; never a replacement for the token."""

        digest = hashlib.sha256(self.token.encode("utf-8")).hexdigest()
        return f"sha256:{digest}"

    def to_wire(self) -> dict[str, Any]:
        """Serialize for the private authenticated RPC envelope."""

        return {
            "lease_id": self.lease_id,
            "document_session_uuid": self.document_session_uuid,
            "generation": self.generation,
            "token": self.token,
        }

    def redacted(self) -> dict[str, Any]:
        """Serialize for logs/status without any token-derived secret."""

        return {
            "lease_id": self.lease_id,
            "document_session_uuid": self.document_session_uuid,
            "generation": self.generation,
        }
