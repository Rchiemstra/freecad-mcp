"""Refresh saved-file identity after an in-place GUI save."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from ..identity_types.identity_mismatch_error import IdentityMismatchError
from ..identity_types.unknown_document_error import UnknownDocumentError
from ..model import DocumentIdentity
from .document_values import document_values
from .path_availability import assert_path_available
from .path_canonicalize import canonicalize_path
from .path_file_identity import file_identity_for_path


def refresh_saved_document(self: Any, document: Any) -> DocumentIdentity:
    """Refresh an exact live proxy after an in-place GUI save.

    FreeCAD may save through an atomic file replacement. The document name,
    path, and Python proxy remain unchanged, but the filesystem identity
    changes. Only that narrow case is accepted here; Save As and replacement
    proxies still require their explicit rebind workflows.
    """

    name, path = document_values(document)
    if not path:
        raise IdentityMismatchError(
            "an unsaved document has no saved-file identity to refresh"
        )
    canonical, comparison = canonicalize_path(path, platform=self.platform)
    file_identity = file_identity_for_path(canonical, platform=self.platform)
    object_key = id(document)
    with self._lock:
        session_uuid = self._objects.get(object_key)
        if session_uuid is None:
            raise UnknownDocumentError(
                "the supplied object is not a registered live document proxy"
            )
        entry = self._entries[session_uuid]
        expected = entry.identity
        if name != expected.name or comparison != expected.comparison_key:
            raise IdentityMismatchError(
                "GUI save changed the document name or path"
            )
        assert_path_available(
            self, comparison, file_identity, except_uuid=session_uuid
        )
        previous_file = expected.file_identity
        if previous_file is not None:
            previous_key = previous_file.comparison_tuple()
            if self._files.get(previous_key) == session_uuid:
                self._files.pop(previous_key, None)
        entry.aliases.add(comparison)
        self._paths[comparison] = session_uuid
        if file_identity is not None:
            self._files[file_identity.comparison_tuple()] = session_uuid
        entry.identity = replace(
            expected,
            canonical_path=canonical,
            comparison_key=comparison,
            file_identity=file_identity,
        )
        return entry.identity
