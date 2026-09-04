from __future__ import annotations

import logging
from typing import Any

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...responses.tool_results import add_screenshot_if_available, tool_fail, tool_ok

logger = logging.getLogger("FreeCADMCPserver")


def _typed_sketch_mutation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    method_name: str,
    args: tuple[object, ...],
    success_message: str,
    failure_prefix: str,
) -> ToolResponse:
    try:
        result = getattr(freecad, method_name)(*args)
    except Exception as exc:
        logger.error("%s: %s", failure_prefix, exc)
        return tool_fail(f"{failure_prefix}: {exc}")
    if not isinstance(result, dict):
        return tool_fail(
            f"{failure_prefix}: invalid RPC response",
            error_code="INVALID_RPC_RESPONSE",
        )
    if result.get("success") is False or result.get("ok") is False:
        return tool_fail(
            f"{failure_prefix}: {result.get('error', result.get('message', 'unknown error'))}",
            structured=result,
            error_code=result.get("error_code"),
        )

    screenshot = None
    if not only_text_feedback:
        try:
            screenshot = freecad.get_active_screenshot()
        except Exception as exc:
            # The typed mutation has already committed; presentation capture
            # cannot safely reclassify it as a retryable model failure.
            result = dict(result)
            result["presentation_warning"] = f"Screenshot capture failed: {exc}"
    response = tool_ok(
        success_message,
        structured=result,
        only_text_feedback=only_text_feedback,
    )
    return add_screenshot_if_available(response, screenshot, only_text_feedback)

def sketch_create_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    body_name: str | None = None,
    attach_to: str | None = None,
    attachment_offset: dict[str, Any] | None = None,
) -> ToolResponse:
    args = (doc_name, sketch_name, body_name, attach_to)
    if attachment_offset is not None:
        args += (attachment_offset,)
    return _typed_sketch_mutation(
        freecad,
        only_text_feedback,
        "sketch_create",
        args,
        f"Sketch '{sketch_name}' created",
        "Failed to create sketch",
    )

def sketch_add_geometry_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    geometry: list,
) -> ToolResponse:
    return _typed_sketch_mutation(
        freecad,
        only_text_feedback,
        "sketch_add_geometry",
        (doc_name, sketch_name, geometry),
        f"Geometry added to '{sketch_name}'",
        "Failed to add geometry",
    )

def sketch_add_constraint_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    constraints: list,
) -> ToolResponse:
    return _typed_sketch_mutation(
        freecad,
        only_text_feedback,
        "sketch_add_constraint",
        (doc_name, sketch_name, constraints),
        f"Constraints added to '{sketch_name}'",
        "Failed to add constraints",
    )

def sketch_delete_constraint_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    constraint_indices: list[int] | None = None,
    constraint_names: list[str] | None = None,
) -> ToolResponse:
    indices = list(constraint_indices or [])
    names = list(constraint_names or [])
    if not indices and not names:
        return tool_fail(
            "Provide at least one constraint index or name",
            error_code="INVALID_ARGUMENT",
        )
    if any(
        isinstance(index, bool) or not isinstance(index, int) or index < 0
        for index in indices
    ):
        return tool_fail(
            "constraint_indices must contain non-negative integers",
            error_code="INVALID_ARGUMENT",
        )
    if any(not isinstance(name, str) or not name for name in names):
        return tool_fail(
            "constraint_names must contain non-empty strings",
            error_code="INVALID_ARGUMENT",
        )
    try:
        result = freecad.sketch_delete_constraint(
            doc_name,
            sketch_name,
            indices,
            names,
        )
        if not isinstance(result, dict):
            return tool_fail(
                "Failed to delete sketch constraints: invalid RPC response",
                error_code="INVALID_RPC_RESPONSE",
            )
        if not result.get("success"):
            return tool_fail(
                f"Failed to delete sketch constraints: {result.get('error', 'unknown error')}",
                structured=result,
                error_code=result.get("error_code"),
            )
        count = int(result.get("deleted_count", len(indices) + len(names)))
        response = tool_ok(
            f"Deleted {count} constraint(s) from '{sketch_name}'",
            structured=result,
        )
        screenshot = (
            None if only_text_feedback else freecad.get_active_screenshot()
        )
        return add_screenshot_if_available(
            response,
            screenshot,
            only_text_feedback,
        )
    except Exception as exc:
        logger.error("Failed to delete sketch constraints: %s", exc)
        return tool_fail(f"Failed to delete sketch constraints: {exc}")

def sketch_delete_geometry_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    geometry_indices: list[int],
) -> ToolResponse:
    indices = list(geometry_indices or [])
    if not indices:
        return tool_fail(
            "geometry_indices must be a non-empty list",
            error_code="INVALID_ARGUMENT",
        )
    if any(
        isinstance(index, bool) or not isinstance(index, int) or index < 0
        for index in indices
    ):
        return tool_fail(
            "geometry_indices must contain non-negative integers",
            error_code="INVALID_ARGUMENT",
        )
    try:
        result = freecad.sketch_delete_geometry(
            doc_name,
            sketch_name,
            indices,
        )
        if not isinstance(result, dict):
            return tool_fail(
                "Failed to delete sketch geometry: invalid RPC response",
                error_code="INVALID_RPC_RESPONSE",
            )
        if not result.get("success"):
            return tool_fail(
                f"Failed to delete sketch geometry: {result.get('error', 'unknown error')}",
                structured=result,
                error_code=result.get("error_code"),
            )
        count = int(result.get("deleted_count", len(set(indices))))
        response = tool_ok(
            f"Deleted {count} geometry item(s) from '{sketch_name}'",
            structured=result,
        )
        screenshot = (
            None if only_text_feedback else freecad.get_active_screenshot()
        )
        return add_screenshot_if_available(
            response,
            screenshot,
            only_text_feedback,
        )
    except Exception as exc:
        logger.error("Failed to delete sketch geometry: %s", exc)
        return tool_fail(f"Failed to delete sketch geometry: {exc}")
