"""Raised when a confirmed new MCP owner must fence an errored local credential."""

from __future__ import annotations

from .lease_service_error import LeaseServiceError


class LockedErrorHandoffRequired(LeaseServiceError):
    """A confirmed new MCP owner must fence an errored local credential."""

    __module__ = "document_lease.service"

    code = "LOCKED_ERROR_HANDOFF_REQUIRED"
