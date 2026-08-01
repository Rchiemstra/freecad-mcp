"""Register live documents in the identity registry."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..identity_types.document_identity_error import DocumentIdentityError
from ..identity_types.duplicate_document_error import DuplicateDocumentError
from ..identity_types.entry import _Entry
from ..identity_types.identity_mismatch_error import IdentityMismatchError
from ..model import DocumentIdentity, FileIdentity
from .document_values import document_values
from .inspect import inspect_registered_document
from .path_availability import assert_path_available
from .path_canonicalize import canonicalize_path
from .path_file_identity import file_identity_for_path

if TYPE_CHECKING:
    from os import PathLike


def register_document(self: Any, document: Any) -> DocumentIdentity:
    name, path = document_values(document)
    object_key = id(document)
    with self._lock:
        known = self._objects.get(object_key)
        if known:
            entry = self._entries[known]
            observed = inspect_registered_document(self, known, document)
            expected = entry.identity
            if (
                observed.name != expected.name
                or observed.comparison_key != expected.comparison_key
                or observed.file_identity != expected.file_identity
            ):
                raise IdentityMismatchError(
                    "live document identity changed outside an explicit "
                    "Save As, reload, or restore rebind"
                )
            return entry.identity
        return _register(self, name=name, path=path, object_key=object_key)


def register(
    self: Any, *, name: str, path: str | PathLike[str] | None = None
) -> DocumentIdentity:
    """Register a live logical document when no proxy object is available."""

    with self._lock:
        return _register(self, name=name, path=path, object_key=None)


def _register(
    self: Any,
    *,
    name: str,
    path: str | PathLike[str] | None,
    object_key: int | None,
) -> DocumentIdentity:
    clean_name = str(name).strip()
    if not clean_name:
        raise DocumentIdentityError("document name must not be empty")
    if clean_name in self._names:
        raise DuplicateDocumentError(f"document name is already live: {clean_name}")
    canonical: str | None = None
    comparison: str | None = None
    file_identity: FileIdentity | None = None
    if path:
        canonical, comparison = canonicalize_path(path, platform=self.platform)
        file_identity = file_identity_for_path(canonical, platform=self.platform)
        assert_path_available(self, comparison, file_identity)
    session_uuid = str(self._uuid_factory())
    identity = DocumentIdentity(
        session_uuid=session_uuid,
        name=clean_name,
        canonical_path=canonical,
        comparison_key=comparison,
        file_identity=file_identity,
    )
    aliases = {comparison} if comparison else set()
    self._entries[session_uuid] = _Entry(identity, object_key, aliases)
    self._names[clean_name] = session_uuid
    if object_key is not None:
        self._objects[object_key] = session_uuid
    if comparison:
        self._paths[comparison] = session_uuid
    if file_identity:
        self._files[file_identity.comparison_tuple()] = session_uuid
    return identity
