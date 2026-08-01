"""Resolve document selectors to a single live registry entry."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..identity_types.document_identity_error import DocumentIdentityError
from ..identity_types.identity_mismatch_error import IdentityMismatchError
from ..identity_types.unknown_document_error import UnknownDocumentError
from ..model import DocumentIdentity, DocumentSelector
from .path_canonicalize import canonicalize_path


def _normalize_selector(
    selector: DocumentSelector | Mapping[str, Any] | str,
) -> DocumentSelector:
    if isinstance(selector, str):
        return DocumentSelector(document_session_uuid=selector)
    if isinstance(selector, Mapping):
        return DocumentSelector(
            document_session_uuid=selector.get("document_session_uuid"),
            document_name=selector.get("document_name"),
            canonical_path=selector.get("canonical_path"),
        )
    return selector


def _resolve_session_uuid(self: Any, selector: DocumentSelector) -> str | None:
    if not selector.document_session_uuid:
        return None
    if selector.document_session_uuid not in self._entries:
        raise UnknownDocumentError(selector.document_session_uuid)
    return selector.document_session_uuid


def _resolve_name(self: Any, selector: DocumentSelector) -> str | None:
    if not selector.document_name:
        return None
    resolved = self._names.get(selector.document_name)
    if not resolved:
        raise UnknownDocumentError(selector.document_name)
    return resolved


def _resolve_path(self: Any, selector: DocumentSelector) -> str | None:
    if not selector.canonical_path:
        return None
    _, comparison = canonicalize_path(
        selector.canonical_path, platform=self.platform
    )
    resolved = self._paths.get(comparison)
    if not resolved:
        raise UnknownDocumentError(selector.canonical_path)
    return resolved


def _assert_consistent_candidates(candidates: list[str]) -> str:
    if not candidates:
        raise DocumentIdentityError("at least one document selector is required")
    if any(candidate != candidates[0] for candidate in candidates[1:]):
        raise IdentityMismatchError(
            "document selector fields identify different live documents"
        )
    return candidates[0]


def resolve(
    self: Any, selector: DocumentSelector | Mapping[str, Any] | str
) -> DocumentIdentity:
    """Resolve every supplied selector assertion to the same live entry."""

    normalized = _normalize_selector(selector)
    with self._lock:
        candidates: list[str] = []
        session = _resolve_session_uuid(self, normalized)
        if session is not None:
            candidates.append(session)
        name_match = _resolve_name(self, normalized)
        if name_match is not None:
            candidates.append(name_match)
        path_match = _resolve_path(self, normalized)
        if path_match is not None:
            candidates.append(path_match)
        session_uuid = _assert_consistent_candidates(candidates)
        return self._entries[session_uuid].identity
