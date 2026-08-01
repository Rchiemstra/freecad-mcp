"""Raised when a confirmed local GUI recovery action could not complete safely."""

from __future__ import annotations

from .lease_service_error import LeaseServiceError


class LocalRecoveryError(LeaseServiceError):
    """A confirmed local GUI recovery action could not complete safely."""

    __module__ = "document_lease.service"

    code = "LOCAL_RECOVERY_FAILED"
