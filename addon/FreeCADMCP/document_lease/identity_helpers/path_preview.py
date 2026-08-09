"""Preview path migrations without publishing registry aliases."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from ..identity_types.unknown_document_error import UnknownDocumentError
from ..model import DocumentIdentity
from .path_availability import assert_path_available
from .path_canonicalize import canonicalize_path
from .path_file_identity import file_identity_for_path

if TYPE_CHECKING:
    from os import PathLike


def preview_path_update(
    self: Any, session_uuid: str, path: str | PathLike[str]
) -> DocumentIdentity:
    """Validate and describe a path migration without publishing aliases."""

    canonical, comparison = canonicalize_path(path, platform=self.platform)
    file_identity = file_identity_for_path(canonical, platform=self.platform)
    with self._lock:
        entry = self._entries.get(session_uuid)
        if entry is None:
            raise UnknownDocumentError(session_uuid)
        assert_path_available(
            self, comparison, file_identity, except_uuid=session_uuid
        )
        return replace(
            entry.identity,
            canonical_path=canonical,
            comparison_key=comparison,
            file_identity=file_identity,
        )
