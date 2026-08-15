from __future__ import annotations

import json
import logging
from typing import Any

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...responses.tool_results import add_screenshot_if_available, json_response, tool_fail, tool_ok

logger = logging.getLogger("FreeCADMCPserver")

def create_object_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_type: str,
    obj_name: str,
    analysis_name: str | None = None,
    obj_properties: dict[str, Any] | None = None,
) -> ToolResponse:
    try:
        obj_data = {
            "Name": obj_name,
            "Type": obj_type,
            "Properties": obj_properties or {},
            "Analysis": analysis_name,
        }
        res = freecad.create_object(doc_name, obj_data)
        if res["success"]:
            response = tool_ok(
                f"Object '{res['object_name']}' created successfully",
                structured=res,
            )
        else:
            response = tool_fail(
                f"Failed to create object: {res['error']}",
                structured=res,
                error_code=res.get("error_code"),
            )
        screenshot = None if only_text_feedback else freecad.get_active_screenshot()
        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    except Exception as e:
        logger.error(f"Failed to create object: {e!s}")
        return tool_fail(f"Failed to create object: {e!s}")

def edit_object_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
    obj_properties: dict[str, Any],
) -> ToolResponse:
    try:
        res = freecad.edit_object(doc_name, obj_name, {"Properties": obj_properties})
        if res["success"]:
            response = tool_ok(
                f"Object '{res['object_name']}' edited successfully",
                structured=res,
            )
        else:
            response = tool_fail(
                f"Failed to edit object: {res['error']}",
                structured=res,
                error_code=res.get("error_code"),
            )
        screenshot = None if only_text_feedback else freecad.get_active_screenshot()
        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    except Exception as e:
        logger.error(f"Failed to edit object: {e!s}")
        return tool_fail(f"Failed to edit object: {e!s}")

def delete_object_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
    recursive: bool = False,
    force: bool = False,
) -> ToolResponse:
    """I5 — delete an object without silently orphaning its dependents (P6).

    FreeCAD's ``Document.removeObject`` deliberately does not remove an object's
    dependents, leaving them Invalid. This op instead:
      * ``recursive=True`` -> remove dependents (leaves first) then the object;
      * ``force=True``      -> remove only the object and report the orphans left;
      * otherwise           -> refuse and list the dependents so the agent decides.

    Returns JSON ``{ok, object, deleted, refused, dependents|orphans_left, ...}``
    with the typed mutation's authoritative health and transaction evidence.
    """
    try:
        result = freecad.delete_object(
            doc_name,
            obj_name,
            recursive,
            force,
        )
    except Exception as e:
        logger.error(f"Failed to delete object: {e!s}")
        return tool_fail(f"Failed to delete object: {e!s}")
    if not isinstance(result, dict):
        return tool_fail(
            "Failed to delete object: invalid RPC response",
            error_code="INVALID_RPC_RESPONSE",
        )
    if result.get("success") is False or result.get("ok") is False:
        return tool_fail(
            f"Failed to delete object: {result.get('error', result.get('message', 'unknown error'))}",
            structured=result,
            error_code=result.get("error_code"),
        )

    screenshot = None
    if not only_text_feedback:
        try:
            screenshot = freecad.get_active_screenshot()
        except Exception as exc:
            # Deletion has already committed. Screenshot capture is
            # presentation-only and must not make the mutation look retryable.
            result = dict(result)
            result["presentation_warning"] = f"Screenshot capture failed: {exc}"
    response = tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=result,
        only_text_feedback=only_text_feedback,
    )
    return add_screenshot_if_available(response, screenshot, only_text_feedback)

def get_objects_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
) -> ToolResponse:
    try:
        response = json_response(freecad.get_objects(doc_name))
        screenshot = None if only_text_feedback else freecad.get_active_screenshot()
        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    except Exception as e:
        logger.error(f"Failed to get objects: {e!s}")
        return tool_fail(f"Failed to get objects: {e!s}")

def get_object_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
) -> ToolResponse:
    try:
        response = json_response(freecad.get_object(doc_name, obj_name))
        screenshot = None if only_text_feedback else freecad.get_active_screenshot()
        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    except Exception as e:
        logger.error(f"Failed to get object: {e!s}")
        return tool_fail(f"Failed to get object: {e!s}")

def get_parts_list_operation(freecad: FreeCADConnection) -> ToolResponse:
    try:
        parts = freecad.get_parts_list()
    except Exception as e:
        logger.error(f"Failed to get parts list: {e!s}")
        return tool_fail(
            f"Failed to get parts list: {e!s}",
            error_code=type(e).__name__.upper(),
        )
    if parts:
        return json_response(parts)
    return json_response(
        {"parts": [], "available": False},
        status="condition_false",
        message=(
            "No parts found in the parts library. You must add parts_library addon."
        ),
    )
