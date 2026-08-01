"""GUI / view / selection RPC method helpers (Phase 4 slice 4G)."""

from .document_ops import list_documents, open_document, reload_document
from .gui_interaction import (
    activate_document,
    get_gui_state,
    get_selection,
    select_subshapes,
    set_section_view,
    set_tree_expanded,
)
from .view_capture import (
    capture_view_sequence,
    capture_view_sequence_to_disk,
    get_active_screenshot,
)
from .view_refresh import animate_placement, refresh_view, repair_view_placements

__all__ = [
    "activate_document",
    "animate_placement",
    "capture_view_sequence",
    "capture_view_sequence_to_disk",
    "get_active_screenshot",
    "get_gui_state",
    "get_selection",
    "list_documents",
    "open_document",
    "refresh_view",
    "reload_document",
    "repair_view_placements",
    "select_subshapes",
    "set_section_view",
    "set_tree_expanded",
]
