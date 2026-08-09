"""Internal registry entry for :class:`DocumentIdentityService`."""

from __future__ import annotations

from dataclasses import dataclass

from ..types.document_identity import DocumentIdentity


@dataclass
class _Entry:
    identity: DocumentIdentity
    object_key: int | None
    aliases: set[str]
