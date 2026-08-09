"""Raised when a dirty document requires local adoption before acquisition."""

from __future__ import annotations

from .lease_service_error import LeaseServiceError


class DirtyAcquisitionError(LeaseServiceError):
    __module__ = "document_lease.service"

    code = "DIRTY_REQUIRES_LOCAL_ADOPTION"
