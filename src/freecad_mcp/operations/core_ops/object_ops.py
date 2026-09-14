from __future__ import annotations

import logging

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...responses.tool_results import add_screenshot_if_available, json_response, tool_fail
from ..parametric_ops.create_object import create_object_operation
from ..parametric_ops.delete_object import delete_object_operation
from ..parametric_ops.edit_object import edit_object_operation

logger = logging.getLogger("FreeCADMCPserver")

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


__all__ = [
    "create_object_operation",
    "delete_object_operation",
    "edit_object_operation",
    "get_object_operation",
    "get_objects_operation",
    "get_parts_list_operation",
]
