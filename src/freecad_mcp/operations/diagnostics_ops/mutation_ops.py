from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...template_resources import render_template_text
from ..p7_assembly import _doc_preamble, _run_json_code
from .helpers import _diag_preamble
from freecad_mcp.operations.parametric_ops.create_placement_binder import (
    create_placement_binder_operation,
)
from freecad_mcp.operations.parametric_ops.create_placement_datum import (
    create_placement_datum_operation,
)
from freecad_mcp.operations.parametric_ops.validate_movement_follow import (
    validate_movement_follow_operation,
)


def run_transaction_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    label: str,
    code: str,
    dry_run: bool = False,
    commit_on_success: bool = True,
) -> ToolResponse:
    preamble = _doc_preamble(doc_name)
    body = render_template_text(
        "diagnostics/run_transaction.py.txt",
        label=repr(label),
        code=repr(code),
        dry_run=repr(dry_run),
        commit_on_success=repr(commit_on_success),
    )
    return _run_json_code(
        freecad, only_text_feedback, "\n".join(preamble) + "\n" + body,
        "Failed to run transaction",
        screenshot=True,
        document=doc_name,
        read_only=False,
    )


__all__ = [
    "create_placement_binder_operation",
    "create_placement_datum_operation",
    "run_transaction_operation",
    "validate_movement_follow_operation",
]
