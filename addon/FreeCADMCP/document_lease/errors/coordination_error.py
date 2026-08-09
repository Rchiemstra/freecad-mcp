"""Raised when lease coordination with the sidecar or peers is lost."""

from __future__ import annotations

from .lease_service_error import LeaseServiceError


class CoordinationError(LeaseServiceError):
    __module__ = "document_lease.service"

    code = "LEASE_COORDINATION_LOST"
