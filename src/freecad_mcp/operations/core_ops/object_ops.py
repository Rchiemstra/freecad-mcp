from __future__ import annotations

import logging
from typing import Any

from ...execute_options import ExecuteOptions
from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...responses.tool_results import add_screenshot_if_available, json_response, tool_fail, tool_ok
from ...template_resources import render_template_lines
from .recompute_log import _RECOMPUTE_LOG_SENTINEL, _format_recompute_log

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
    plus the I3 recompute log so any newly-Invalid objects surface immediately.
    """
    try:
        code = "\n".join(
            render_template_lines(
                "core/delete_object.py.txt",
                doc_name=repr(doc_name),
                obj_name=repr(obj_name),
                recursive=repr(recursive),
                force=repr(force),
            )
            + render_template_lines("diagnostics/recompute_log.py.txt")
        )
        res = freecad.execute_code(
            code,
            ExecuteOptions(
                document=doc_name,
                affected_documents=[doc_name],
                recompute="target",
                recompute_documents=[doc_name],
                generated_operation=True,
                operation_id="delete_object",
            ),
        )
        screenshot = freecad.get_active_screenshot()
        if res["success"]:
            output = res.get("message", "")
            marker = "Output:"
            if marker in output:
                output = output.split(marker, 1)[1].strip()
            # Split the delete JSON from the I3 recompute-log sentinel.
            log_summary = _format_recompute_log(output)
            json_part = output
            idx = output.rfind(_RECOMPUTE_LOG_SENTINEL)
            if idx >= 0:
                json_part = output[:idx].rstrip()
            msg = json_part
            if log_summary:
                msg += "\n" + log_summary
            response = tool_ok(msg, structured=res)
        else:
            response = tool_fail(
                f"Failed to delete object: {res.get('error', res.get('message', 'unknown error'))}",
                structured=res,
                error_code=res.get("error_code"),
            )
        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    except Exception as e:
        logger.error(f"Failed to delete object: {e!s}")
        return tool_fail(f"Failed to delete object: {e!s}")

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
