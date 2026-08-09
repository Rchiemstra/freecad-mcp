"""Raised when live document or saved file no longer matches lease authority."""

from __future__ import annotations

from .clean_release_error import CleanReleaseError


class LiveDocumentValidationError(CleanReleaseError):
    """The live document or saved file no longer matches lease authority."""

    __module__ = "document_lease.service"

    code = "LIVE_DOCUMENT_VALIDATION_FAILED"
