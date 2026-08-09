"""Remove live documents from the identity registry."""

from __future__ import annotations

from typing import Any

from ..identity_types.unknown_document_error import UnknownDocumentError
from ..model import DocumentIdentity


def unregister(self: Any, session_uuid: str) -> DocumentIdentity:
    with self._lock:
        entry = self._entries.pop(session_uuid, None)
        if entry is None:
            raise UnknownDocumentError(session_uuid)
        self._names.pop(entry.identity.name, None)
        if entry.object_key is not None:
            self._objects.pop(entry.object_key, None)
        for alias in entry.aliases:
            if self._paths.get(alias) == session_uuid:
                self._paths.pop(alias, None)
        for key, owner in list(self._files.items()):
            if owner == session_uuid:
                self._files.pop(key, None)
        return entry.identity


def list_identities(self: Any) -> list[DocumentIdentity]:
    with self._lock:
        return [entry.identity for entry in self._entries.values()]
