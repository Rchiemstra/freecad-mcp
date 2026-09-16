from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...responses.tool_results import json_response, tool_fail
from ..parametric_ops.edge_axis import edge_axis_operation as _typed_edge_axis
from ..parametric_ops.face_normal import face_normal_operation as _typed_face_normal


def _typed_json(freecad: FreeCADConnection, method: str, fail: str, *args: object, **kwargs: object) -> ToolResponse:
    try:
        raw = getattr(freecad, method)(*args, **kwargs)
    except Exception as exc:
        return tool_fail(f"{fail}: {exc}")
    if isinstance(raw, dict) and raw.get("success") is False:
        return tool_fail(
            f"{fail}: " + str(raw.get("error", "unknown")),
            structured=raw,
            error_code=str(raw.get("error_code", "QUERY_FAILED")),
        )
    return json_response(raw if isinstance(raw, dict) else {"ok": True, "payload": raw})


def find_faces_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    object_name: str,
    type: str | None = None,
    normal_approx: dict | list | None = None,
    center_approx: dict | list | None = None,
    radius: float | None = None,
    tol: float = 1e-3,
    center_tol: float = 1.0,
    limit: int = 10,
) -> ToolResponse:
    del only_text_feedback
    return _typed_json(
        freecad,
        "find_faces",
        "Failed to find faces",
        doc_name,
        object_name,
        type=type,
        normal_approx=normal_approx,
        center_approx=center_approx,
        radius=radius,
        tol=tol,
        center_tol=center_tol,
        limit=limit,
    )


def find_edges_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    object_name: str,
    type: str | None = None,
    direction_approx: dict | list | None = None,
    center_approx: dict | list | None = None,
    radius: float | None = None,
    tol: float = 1e-3,
    center_tol: float = 1.0,
    limit: int = 10,
) -> ToolResponse:
    del only_text_feedback
    return _typed_json(
        freecad,
        "find_edges",
        "Failed to find edges",
        doc_name,
        object_name,
        type=type,
        normal_approx=direction_approx,
        center_approx=center_approx,
        radius=radius,
        tol=tol,
        center_tol=center_tol,
        limit=limit,
    )


def face_normal_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    object_name: str,
    face: str,
) -> ToolResponse:
    del only_text_feedback
    return _typed_face_normal(freecad, doc_name, object_name, face)


def edge_axis_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    object_name: str,
    edge: str,
) -> ToolResponse:
    del only_text_feedback
    return _typed_edge_axis(freecad, doc_name, object_name, edge)


def subshape_pose_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    object_name: str,
    subshape: str,
) -> ToolResponse:
    del only_text_feedback
    if subshape.startswith("Face"):
        return _typed_face_normal(freecad, doc_name, object_name, subshape)
    return _typed_edge_axis(freecad, doc_name, object_name, subshape)
