from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LeaseCredential:
    lease_id: str
    document_session_uuid: str
    generation: int
    # Credentials may be included in exception context or diagnostic object
    # reprs.  Keep the bearer secret out of those generic representations;
    # acquisition and authenticated wire serialization are the only intended
    # raw-token boundaries.
    token: str = field(repr=False)
    # Populated by the addon from the authenticated transport context, never
    # trusted from the caller's envelope payload.
    mcp_instance_id: str

LeaseCredential.__module__ = "document_lease.model"
