from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Part3IdentitySelector:
    """Part 3 identity-bound document selector (not the lease DocumentSelector)."""

    document_uid: str
    document_instance_id: int
    lifecycle_epoch: int
    document_name: str | None = None


Part3IdentitySelector.__module__ = "part3_collaboration.types"
