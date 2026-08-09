"""Base runtime error for document lease service operations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class LeaseServiceError(RuntimeError):
    __module__ = "document_lease.service"

    code = "LEASE_SERVICE_ERROR"

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None):
        self.details = dict(details or {})
        super().__init__(message)
