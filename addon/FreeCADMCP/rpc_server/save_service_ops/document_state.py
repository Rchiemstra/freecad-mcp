"""FreeCAD document dirty-state helpers for save_service."""

from __future__ import annotations

from typing import Any

try:
    from document_state import (
        DocumentDirtyStateUnavailable,
        document_modified_state,
        gui_document_for,
        require_document_modified,
        set_document_modified,
    )
except ImportError:
    from addon.FreeCADMCP.document_state import (
        DocumentDirtyStateUnavailable,
        document_modified_state,
        gui_document_for,
        require_document_modified,
        set_document_modified,
    )

def _document_filename(document: Any) -> str | None:
    value = getattr(document, "FileName", None)
    if not value:
        return None
    return str(value)


def _document_is_dirty(document: Any) -> bool:
    return require_document_modified(document)


def _clear_document_modified_after_save(document: Any) -> None:
    """Mirror Gui::Document save commands after direct App save calls."""

    try:
        set_document_modified(document, False)
    except DocumentDirtyStateUnavailable:
        if gui_document_for(document) is not None:
            raise
        # Compatibility App fakes clear their own flag.  Preserve a true flag
        # so the subsequent strict check raises DocumentDirtyError rather than
        # masking a simulated save that remained dirty.
        if document_modified_state(document) is None:
            raise
