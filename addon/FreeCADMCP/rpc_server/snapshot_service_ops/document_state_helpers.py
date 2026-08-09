"""GUI selection and document state probes for snapshot invariants."""

from __future__ import annotations

from contextlib import suppress
from typing import Any

import FreeCADGui

try:
    from document_state import document_modified_state
except ImportError:
    from addon.FreeCADMCP.document_state import document_modified_state


def selection_state() -> list[tuple[str, str, tuple[str, ...]]]:
    try:
        return [
            (
                item.DocumentName,
                item.ObjectName,
                tuple(str(name) for name in getattr(item, "SubElementNames", [])),
            )
            for item in FreeCADGui.Selection.getSelectionEx()
        ]
    except Exception:
        return []


def document_state(doc) -> dict[str, Any]:
    dependencies = []
    with suppress(Exception):
        dependencies = sorted(item.Name for item in doc.getDependentDocuments())
    return {
        "document_name": doc.Name,
        "document_label": getattr(doc, "Label", doc.Name),
        "document_uid": str(getattr(doc, "Uid", "")),
        "document_id": str(getattr(doc, "Id", "")),
        "original_filename": getattr(doc, "FileName", ""),
        "modified": document_modified_state(doc),
        "object_count": len(getattr(doc, "Objects", [])),
        "dependencies": dependencies,
        "has_pending_transaction": bool(getattr(doc, "HasPendingTransaction", False)),
        "transacting": bool(getattr(doc, "Transacting", False)),
        "last_modified_date": str(getattr(doc, "LastModifiedDate", "")),
    }
