from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...responses.tool_results import tool_fail
from freecad_mcp.operations.parametric_ops.create_placement_binder import (
    create_placement_binder_operation,
)
from freecad_mcp.operations.parametric_ops.create_placement_datum import (
    create_placement_datum_operation,
)
from freecad_mcp.operations.parametric_ops.run_transaction import (
    run_transaction_operation,
)


def validate_movement_follow_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    source: str,
    dependents: object,
    translation: object,
    axis: object,
    angle_deg: float,
    restore: bool = True,
    tolerance: float = 1e-7,
) -> ToolResponse:
    """Reject generated two-recompute probes; the public MCP tool uses typed JSON-RPC."""

    del (
        freecad,
        only_text_feedback,
        doc_name,
        source,
        dependents,
        translation,
        axis,
        angle_deg,
        restore,
        tolerance,
    )
    return tool_fail(
        "Movement-follow validation requires mutation work on both sides of "
        "recompute and cannot run atomically through the native coordinator.",
        error_code="UNSUPPORTED_NATIVE_PHASE_BOUNDARY",
        structured={
            "success": False,
            "ok": False,
            "error_code": "UNSUPPORTED_NATIVE_PHASE_BOUNDARY",
            "operation": "validate_movement_follow",
            "retryable": False,
        },
    )


__all__ = [
    "create_placement_binder_operation",
    "create_placement_datum_operation",
    "run_transaction_operation",
    "validate_movement_follow_operation",
]
