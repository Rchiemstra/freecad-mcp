from __future__ import annotations

import logging

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...responses.tool_results import add_screenshot_if_available, tool_fail, tool_ok
from ...template_resources import render_template_lines, render_template_text
from .code_gen import _constraint_line, _geom_line
from .run_code import _run_code

logger = logging.getLogger("FreeCADMCPserver")

def sketch_create_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    body_name: str | None = None,
    attach_to: str | None = None,
) -> ToolResponse:
    attachment_code = ""
    if attach_to:
        if attach_to in ("XY_Plane", "XZ_Plane", "YZ_Plane"):
            attachment_code = render_template_text(
                "core/attach_origin_plane.py.txt",
                attach_to=repr(attach_to),
            ).strip()
        elif ":" in attach_to:
            obj_n, face = attach_to.split(":", 1)
            attachment_code = render_template_text(
                "core/attach_face.py.txt",
                obj_name=repr(obj_n),
                face_name=repr(face),
            ).strip()
    lines = render_template_lines(
        "core/sketch_create.py.txt",
        doc_name=repr(doc_name),
        doc_missing=repr(f"Document {doc_name!r} not found"),
        body_name=repr(body_name),
        body_missing=repr(f"Body {body_name!r} not found"),
        sketch_name=repr(sketch_name),
        attachment_code=attachment_code,
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Sketch '{sketch_name}' created", "Failed to create sketch",
                     document=doc_name)

def sketch_add_geometry_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    geometry: list,
) -> ToolResponse:
    lines = render_template_lines(
        "core/sketch_add_geometry.py.txt",
        doc_name=repr(doc_name),
        sketch_name=repr(sketch_name),
        geometry_lines="\n".join(_geom_line("", geom) for geom in geometry),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Geometry added to '{sketch_name}'", "Failed to add geometry",
                     document=doc_name)

def sketch_add_constraint_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    constraints: list,
) -> ToolResponse:
    lines = render_template_lines(
        "core/sketch_add_constraint.py.txt",
        doc_name=repr(doc_name),
        sketch_name=repr(sketch_name),
        constraint_lines="\n".join(_constraint_line(c) for c in constraints),
        message=repr(f"{len(constraints)} constraint(s) added"),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Constraints added to '{sketch_name}'", "Failed to add constraints",
                     document=doc_name)

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
