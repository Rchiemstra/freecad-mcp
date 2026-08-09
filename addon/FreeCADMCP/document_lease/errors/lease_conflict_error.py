"""Raised when lease acquisition or mutation conflicts with current authority."""

from __future__ import annotations

from .lease_service_error import LeaseServiceError


class LeaseConflictError(LeaseServiceError):
    __module__ = "document_lease.service"

    code = "LEASE_CONFLICT"
