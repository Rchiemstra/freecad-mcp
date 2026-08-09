from __future__ import annotations

from typing import Any

_LOCAL_SAVE_GUI_TIMEOUT = 120.0


def _mcp_dock_features(dock_widget_type: Any) -> Any:
    """Keep the MCP details panel docked inside the FreeCAD main window."""

    return (
        dock_widget_type.DockWidgetClosable
        | dock_widget_type.DockWidgetMovable
    )


_AGENT_OWNED_STATES = frozenset(
    {
        "ACQUIRING",
        "LOCKED_IDLE",
        "LOCKED_EDITING",
        "LOCKED_RECOMPUTING",
        "LOCKED_SAVING",
        "LOCKED_ERROR",
        "CANCELLING",
        "RELEASING",
        "STALE",
    }
)
_MUTATING_ACTION_NAMES = frozenset(
    {
        "Std_Undo",
        "Std_Redo",
        "Std_Cut",
        "Std_Paste",
        "Std_Delete",
        "Std_DuplicateSelection",
        "Std_Save",
        "Std_SaveAll",
        "Std_SaveAs",
        "Std_SaveCopy",
        "Std_Revert",
        "Std_CloseActiveWindow",
        "Std_CloseAllWindows",
        "Std_Import",
        "Std_MergeProjects",
        "Std_Edit",
        "Std_Transform",
        "Std_TransformManip",
        "Std_DlgMacroRecord",
        "Std_DlgMacroExecute",
        "Std_DlgMacroExecuteDirect",
        "Std_MacroExecute",
        "Std_MacroRecord",
    }
)
_MUTATING_ACTION_PREFIXES = (
    "PartDesign_",
    "Sketcher_",
    "Part_",
    "Draft_",
    "Arch_",
    "BIM_",
)

_SECRET_FIELD_NAMES = frozenset(
    {
        "token",
        "lease_token",
        "session_token",
        "rpc_session_token",
        "auth_secret",
        "secret",
        "token_fingerprint",
    }
)
