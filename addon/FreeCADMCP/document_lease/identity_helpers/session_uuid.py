"""Resolve the session UUID bound to an exact live document proxy."""

from __future__ import annotations

from typing import Any

from ..identity_types.unknown_document_error import UnknownDocumentError


def registered_session_uuid(self: Any, document: Any) -> str:
    """Return the session bound to this exact live proxy.

    Unlike name or path resolution, this remains usable when the proxy's
    observed saved-file identity no longer matches the registered entry.
    Recovery code can therefore locate the affected entry without ever
    resolving an arbitrary replacement proxy by a reusable document name.
    """

    object_key = id(document)
    with self._lock:
        session_uuid = self._objects.get(object_key)
        if session_uuid is None or session_uuid not in self._entries:
            raise UnknownDocumentError(
                "the supplied object is not a registered live document proxy"
            )
        return session_uuid
