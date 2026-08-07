from __future__ import annotations

import json
import logging
from typing import Any

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...responses.tool_results import add_screenshot_if_available, json_response, tool_fail, tool_ok

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

def repair_references_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    repairs: list[dict[str, Any]],
    *,
    recompute: bool = False,
    validate: bool = False,
) -> ToolResponse:
    """Atomically repair link properties, with recompute deferred by default."""
    try:
        result = freecad.repair_references(
            doc_name,
            repairs,
            recompute=recompute,
            validate=validate,
        )
        if result.get("ok"):
            return json_response(result)
        return tool_fail(
            json.dumps(result, ensure_ascii=False, indent=2, default=str),
            structured=result,
        )
    except Exception as exc:
        logger.error("Failed to repair references: %s", exc)
        return tool_fail(f"Failed to repair references: {exc}")

def insert_part_from_library_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    relative_path: str,
) -> ToolResponse:
    try:
        res = freecad.insert_part_from_library(doc_name, relative_path)
        if res["success"]:
            response = tool_ok(
                f"Part inserted from library: {res['message']}",
                structured=res,
            )
        else:
            response = tool_fail(
                f"Failed to insert part from library: {res['error']}",
                structured=res,
                error_code=res.get("error_code"),
            )
        screenshot = None if only_text_feedback else freecad.get_active_screenshot()
        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    except Exception as e:
        logger.error(f"Failed to insert part from library: {e!s}")
        return tool_fail(f"Failed to insert part from library: {e!s}")
