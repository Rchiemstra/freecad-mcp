from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from freecad_mcp.operations.parametric_ops.create_placement_binder import (
    create_placement_binder_operation,
)
from freecad_mcp.operations.parametric_ops.create_placement_datum import (
    create_placement_datum_operation,
)
from freecad_mcp.operations.parametric_ops.run_transaction import (
    run_transaction_operation as _typed_run_transaction,
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
    return _typed_run_transaction(
        freecad, only_text_feedback, doc_name, label, code, dry_run, commit_on_success
    )


__all__ = [
    "create_placement_binder_operation",
    "create_placement_datum_operation",
    "run_transaction_operation",
    "validate_movement_follow_operation",
]
