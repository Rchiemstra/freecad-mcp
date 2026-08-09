"""Raised when the current lease state forbids the requested operation."""

from __future__ import annotations

from .lease_service_error import LeaseServiceError


class LeaseStateError(LeaseServiceError):
    __module__ = "document_lease.service"

    code = "LEASE_STATE_FORBIDS_OPERATION"
