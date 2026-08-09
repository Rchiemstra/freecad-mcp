"""Reject paths and file identities already owned by a live document."""

from __future__ import annotations

from typing import Any

from ..identity_types.duplicate_document_error import DuplicateDocumentError
from ..model import FileIdentity


def assert_path_available(
    self: Any,
    comparison: str,
    file_identity: FileIdentity | None,
    *,
    except_uuid: str | None = None,
) -> None:
    path_owner = self._paths.get(comparison)
    if path_owner and path_owner != except_uuid:
        raise DuplicateDocumentError(
            f"another live document already uses path {comparison}"
        )
    if file_identity:
        file_owner = self._files.get(file_identity.comparison_tuple())
        if file_owner and file_owner != except_uuid:
            raise DuplicateDocumentError(
                "another live document already uses the same filesystem file"
            )
