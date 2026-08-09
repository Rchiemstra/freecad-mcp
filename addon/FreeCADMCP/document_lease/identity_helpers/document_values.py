"""Read name and path fields from a live FreeCAD document proxy."""

from __future__ import annotations

from typing import Any

from ..identity_types.document_identity_error import DocumentIdentityError


def document_values(document: Any) -> tuple[str, str | None]:
    name = getattr(document, "Name", None) or getattr(document, "Label", None)
    if not name:
        raise DocumentIdentityError("live document has no Name")
    path = getattr(document, "FileName", None) or None
    return str(name), str(path) if path else None
