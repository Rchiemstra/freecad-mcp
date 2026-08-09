"""Inspect a registered live document proxy without mutating registry maps."""

from __future__ import annotations

from typing import Any

from ..identity_types.identity_mismatch_error import IdentityMismatchError
from ..identity_types.unknown_document_error import UnknownDocumentError
from ..model import DocumentIdentity, FileIdentity
from .document_values import document_values
from .path_canonicalize import canonicalize_path
from .path_file_identity import file_identity_for_path


def inspect_registered_document(
    self: Any, session_uuid: str, document: Any
) -> DocumentIdentity:
    """Describe a registered live proxy without changing its identity maps.

    This is deliberately separate from :func:`register_document`: safety
    preflights must observe an unexpected Save As/path replacement rather than
    silently accepting it as a new alias.
    """

    name, path = document_values(document)
    object_key = id(document)
    with self._lock:
        entry = self._entries.get(session_uuid)
        if entry is None:
            raise UnknownDocumentError(session_uuid)
        if entry.object_key is None or entry.object_key != object_key:
            raise IdentityMismatchError(
                "the supplied object is not the registered live document proxy"
            )
        canonical: str | None = None
        comparison: str | None = None
        file_identity: FileIdentity | None = None
        if path:
            canonical, comparison = canonicalize_path(path, platform=self.platform)
            file_identity = file_identity_for_path(
                canonical, platform=self.platform
            )
        return DocumentIdentity(
            session_uuid=session_uuid,
            name=name,
            canonical_path=canonical,
            comparison_key=comparison,
            file_identity=file_identity,
        )
