"""One-class document identity error types."""

from .document_identity_error import DocumentIdentityError
from .duplicate_document_error import DuplicateDocumentError
from .identity_mismatch_error import IdentityMismatchError
from .unknown_document_error import UnknownDocumentError

__all__ = [
    "DocumentIdentityError",
    "DuplicateDocumentError",
    "IdentityMismatchError",
    "UnknownDocumentError",
]
