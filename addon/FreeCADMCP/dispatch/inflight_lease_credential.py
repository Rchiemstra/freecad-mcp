"""Private request credential; its bearer token is never represented."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class InflightLeaseCredential:
    """Private request credential; its bearer token is never represented."""

    lease_id: str
    document_session_uuid: str
    generation: int
    token: str = field(repr=False)
    mcp_instance_id: str = ""
