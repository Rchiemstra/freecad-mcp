"""Raised when a same-FreeCAD lease has safely recoverable inactive authority."""

from __future__ import annotations

from .lease_service_error import LeaseServiceError


class OrphanedLocalMcpRecoveryRequired(LeaseServiceError):
    """A same-FreeCAD lease has safely recoverable inactive authority."""

    __module__ = "document_lease.service"

    code = "ORPHANED_LOCAL_MCP_RECOVERY_REQUIRED"
