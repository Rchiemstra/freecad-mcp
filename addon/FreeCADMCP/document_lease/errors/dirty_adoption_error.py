"""Raised when dirty adoption preconditions are not satisfied."""

from __future__ import annotations

from .lease_service_error import LeaseServiceError


class DirtyAdoptionError(LeaseServiceError):
    __module__ = "document_lease.service"

    code = "DIRTY_ADOPTION_PRECONDITION_FAILED"
