"""Raised when clean release preconditions are not satisfied."""

from __future__ import annotations

from .lease_service_error import LeaseServiceError


class CleanReleaseError(LeaseServiceError):
    __module__ = "document_lease.service"

    code = "CLEAN_RELEASE_PRECONDITION_FAILED"
