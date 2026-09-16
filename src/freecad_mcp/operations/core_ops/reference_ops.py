from __future__ import annotations

import json
import logging

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...responses.tool_results import json_response, tool_fail
from ..parametric_ops.insert_part_from_library import insert_part_from_library_operation
from ..parametric_ops.repair_references import repair_references_operation

logger = logging.getLogger("FreeCADMCPserver")


def inspect_references_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    object_names: list[str] | None = None,
    *,
    only_invalid: bool = False,
    validate: bool = False,
) -> ToolResponse:
    """Inspect raw link properties without requesting shapes or a recompute."""
    try:
        result = freecad.inspect_references(
            doc_name,
            object_names,
            only_invalid=only_invalid,
            validate=validate,
        )
        if result.get("ok"):
            return json_response(result)
        return tool_fail(
            json.dumps(result, ensure_ascii=False, indent=2, default=str),
            structured=result,
        )
    except Exception as exc:
        logger.error("Failed to inspect references: %s", exc)
        return tool_fail(f"Failed to inspect references: {exc}")


__all__ = [
    "insert_part_from_library_operation",
    "inspect_references_operation",
    "repair_references_operation",
]
