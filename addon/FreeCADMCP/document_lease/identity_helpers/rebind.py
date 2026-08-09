"""Attach a replacement proxy after a lease-preserving reload or restore."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from ..identity_types.duplicate_document_error import DuplicateDocumentError
from ..identity_types.unknown_document_error import UnknownDocumentError
from ..model import DocumentIdentity
from .document_values import document_values
from .path_availability import assert_path_available
from .path_canonicalize import canonicalize_path
from .path_file_identity import file_identity_for_path
from .path_update import update_path


def _validate_replacement_path(
    self: Any, session_uuid: str, path: str
) -> None:
    _, comparison = canonicalize_path(path, platform=self.platform)
    file_identity = file_identity_for_path(path, platform=self.platform)
    assert_path_available(
        self, comparison, file_identity, except_uuid=session_uuid
    )


def rebind_document(self: Any, session_uuid: str, document: Any) -> DocumentIdentity:
    """Attach a replacement proxy after a lease-preserving reload/restore."""

    name, path = document_values(document)
    object_key = id(document)
    with self._lock:
        entry = self._entries.get(session_uuid)
        if entry is None:
            raise UnknownDocumentError(session_uuid)
        other = self._objects.get(object_key)
        if other and other != session_uuid:
            raise DuplicateDocumentError("replacement proxy is already registered")
        existing_name = self._names.get(name)
        if existing_name and existing_name != session_uuid:
            raise DuplicateDocumentError(name)
        # Validate the replacement path before changing object/name indexes,
        # so a duplicate path cannot leave a partially rebound entry.
        if path:
            _validate_replacement_path(self, session_uuid, path)
        if entry.object_key is not None:
            self._objects.pop(entry.object_key, None)
        if name != entry.identity.name:
            self._names.pop(entry.identity.name, None)
            self._names[name] = session_uuid
            entry.identity = replace(entry.identity, name=name)
        entry.object_key = object_key
        self._objects[object_key] = session_uuid
        if path:
            return update_path(self, session_uuid, path)
        return entry.identity
