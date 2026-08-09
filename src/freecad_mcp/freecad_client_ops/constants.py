"""FreeCAD client constants."""

from __future__ import annotations

from ..template_resources import read_template_text

SCREENSHOT_SUPPORT_CHECK = read_template_text(
    "freecad_client/screenshot_support_check.py.txt"
)

DIRECT_READ_METHODS = frozenset(
    {
        "ping",
        "check_rpc_sync",
        "get_instance_info",
        "get_worker_status",
        "cancel_worker_job",
        "get_document_lock",
        "list_document_locks",
        "inspect_references",
        "get_active_screenshot",
        "capture_view_sequence",
        "capture_view_sequence_to_disk",
        "refresh_view",
        "get_objects",
        "get_object",
        "get_parts_list",
        "list_documents",
        "open_document",
        "activate_document",
        "set_tree_expanded",
        "select_subshapes",
        "get_selection",
        "get_gui_state",
        "set_section_view",
        "spreadsheet_get_cells",
        "spreadsheet_list_aliases",
        "list_expressions",
        "diagnose_parametric",
    }
)
