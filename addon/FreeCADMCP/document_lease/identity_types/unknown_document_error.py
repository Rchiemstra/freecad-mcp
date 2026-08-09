"""Raised when a document selector does not resolve to a live entry."""

from __future__ import annotations

from .document_identity_error import DocumentIdentityError


class UnknownDocumentError(DocumentIdentityError):
    __module__ = "document_lease.identity"
