"""LeaseRevocation — extracted from lease_manager."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class LeaseRevocation:
    """Non-secret tombstone explaining why a local credential was discarded."""

    document_session_uuid: str
    lease_id: str
    generation: int
    reason: str
    user_intervened: bool = False
    revoked_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
