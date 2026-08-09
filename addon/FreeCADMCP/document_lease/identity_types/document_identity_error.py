"""Base error for stable live-document identity operations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class DocumentIdentityError(ValueError):
    __module__ = "document_lease.identity"
    code = "DOCUMENT_IDENTITY_ERROR"

    def __init__(
        self, message: str, *, details: Mapping[str, Any] | None = None
    ) -> None:
        self.details = dict(details or {})
        super().__init__(message)
