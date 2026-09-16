"""FreeCAD client constants."""

from __future__ import annotations

SCREENSHOT_SUPPORT_CHECK = '''import FreeCAD
import FreeCADGui

if FreeCAD.Gui.ActiveDocument and FreeCAD.Gui.ActiveDocument.ActiveView:
    view_type = type(FreeCAD.Gui.ActiveDocument.ActiveView).__name__

    # These view types don't support screenshots
    unsupported_views = ['SpreadsheetGui::SheetView', 'DrawingGui::DrawingView', 'TechDrawGui::MDIViewPage']

    if view_type in unsupported_views or not hasattr(FreeCAD.Gui.ActiveDocument.ActiveView, 'saveImage'):
        print("Current view does not support screenshots")
        False
    else:
        print(f"Current view supports screenshots: {view_type}")
        True
else:
    print("No active view")
    False
'''

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
