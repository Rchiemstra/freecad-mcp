from __future__ import annotations

from mcp.types import CallToolResult

from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail


def run_transaction_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    label: str,
    code: str,
    dry_run: bool = False,
    commit_on_success: bool = True,
) -> CallToolResult:
    """Fail closed: generated callbacks may not own native transaction control."""

    del freecad, only_text_feedback, doc_name, label, code, dry_run, commit_on_success
    return tool_fail(
        "run_transaction is retired because nested transaction control is incompatible "
        "with FreeCAD's native mutation coordinator; use typed modelling tools instead.",
        error_code="RUN_TRANSACTION_RETIRED",
        structured={
            "success": False,
            "ok": False,
            "error_code": "RUN_TRANSACTION_RETIRED",
            "error": (
                "Generated mutation callbacks cannot open, commit, abort, undo, or redo "
                "inside the native coordinator. Use typed modelling tools."
            ),
        },
    )
