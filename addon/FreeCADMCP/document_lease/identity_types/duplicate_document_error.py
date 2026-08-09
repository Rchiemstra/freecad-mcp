"""Raised when a name, path, or file identity is already live."""

from __future__ import annotations

from .document_identity_error import DocumentIdentityError


class DuplicateDocumentError(DocumentIdentityError):
    __module__ = "document_lease.identity"
