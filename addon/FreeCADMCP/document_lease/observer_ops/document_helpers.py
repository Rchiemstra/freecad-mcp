"""Document resolution and dirty-state helpers for observer callbacks."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    from document_state import document_modified_state
except ImportError:
    from addon.FreeCADMCP.document_state import document_modified_state


def document_from_subject(subject: Any) -> Any | None:
    """Resolve App::Document from an App object, GUI view provider, or doc."""

    if subject is None:
        return None
    if getattr(subject, "Name", None) and hasattr(subject, "FileName"):
        return subject
    document = getattr(subject, "Document", None)
    if document is not None:
        return document
    app_object = getattr(subject, "Object", None)
    document = getattr(app_object, "Document", None)
    if document is not None:
        return document
    get_document = getattr(subject, "getDocument", None)
    if callable(get_document):
        try:
            document = get_document()
        except Exception:
            document = None
        if document is not None and not isinstance(document, str):
            return document
    return None


def document_keys(document: Any, identity: Any | None = None) -> tuple[str, ...]:
    """Return exact aliases against which GUI request scope is checked."""

    values: list[str] = []
    if identity is not None:
        for attribute in (
            "session_uuid",
            "name",
            "canonical_path",
            "comparison_key",
        ):
            value = str(getattr(identity, attribute, "") or "").strip()
            if value and value not in values:
                values.append(value)
    name = str(getattr(document, "Name", "") or "").strip()
    if name and name not in values:
        values.append(name)
    filename = str(getattr(document, "FileName", "") or "").strip()
    if filename:
        values.append(filename)
        try:
            resolved = str(Path(filename).resolve())
            if resolved not in values:
                values.append(resolved)
            normalized = os.path.normcase(resolved)
            if normalized not in values:
                values.append(normalized)
        except (OSError, RuntimeError, ValueError):
            pass
    return tuple(values)


def document_dirty(document: Any) -> bool | None:
    return document_modified_state(document)


def document_display_name(document: Any) -> str:
    name = getattr(document, "Name", None) or getattr(document, "Label", None)
    return str(name or "<unknown>")
