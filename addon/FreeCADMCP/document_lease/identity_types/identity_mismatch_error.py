"""Raised when selector fields or live proxies disagree."""

from __future__ import annotations

from .document_identity_error import DocumentIdentityError


class IdentityMismatchError(DocumentIdentityError):
    __module__ = "document_lease.identity"
