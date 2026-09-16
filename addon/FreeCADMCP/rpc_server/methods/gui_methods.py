"""GUI / view / selection RPC methods bound on ``FreeCADRPC``."""

from __future__ import annotations

from .cad_methods_ops.activate_document import rpc_activate_document as activate_document
from .cad_methods_ops.open_document import rpc_open_document as open_document
from .cad_methods_ops.reload_document import rpc_reload_document as reload_document
from .gui_methods_ops.document_ops import list_documents
from .gui_methods_ops.gui_interaction import (
    get_gui_state,
    get_report_view,
    get_selection,
    select_subshapes,
    set_section_view,
    set_tree_expanded,
)
from .gui_methods_ops.view_capture import (
    capture_view_sequence,
    capture_view_sequence_to_disk,
    get_active_screenshot,
)
from .gui_methods_ops.view_refresh import (
    animate_placement,
    refresh_view,
    repair_view_placements,
)

__all__ = [
    "activate_document",
    "animate_placement",
    "capture_view_sequence",
    "capture_view_sequence_to_disk",
    "get_active_screenshot",
    "get_gui_state",
    "get_report_view",
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
