"""Raised when a lease credential or owner fails authorization."""

from __future__ import annotations

from .lease_service_error import LeaseServiceError


class AuthorizationError(LeaseServiceError):
    __module__ = "document_lease.service"

    code = "LEASE_AUTHORIZATION_FAILED"
