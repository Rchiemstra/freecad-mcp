from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.create_datum_plane_contract import (
    make_create_datum_plane_failure,
    make_create_datum_plane_uncertain,
    parse_create_datum_plane_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def create_datum_plane_operation(
    freecad: FreeCADConnection, only_text_feedback: bool, doc_name: str, plane_name: str, body_name: str, mode: str, source_ref: str | None = None, face_a: str | None = None, face_b: str | None = None, offset_along_normal: object = None, map_mode: str = "FlatFace", if_exists: str = "error",
) -> CallToolResult:
    if if_exists not in {"error", "skip", "replace"}:
        failure = make_create_datum_plane_failure("INVALID_ARGUMENT", "if_exists must be one of: error, skip, replace")
        return tool_fail(failure["error"], structured=dict(failure), error_code=failure["error_code"])
    try:
        raw_result: object = freecad._invoke_mutation_v2(
            "create_datum_plane",
            {
            "doc_name": doc_name,
            "plane_name": plane_name,
            "body_name": body_name,
            "mode": mode,
            "source_ref": source_ref,
            "face_a": face_a,
            "face_b": face_b,
            "offset_along_normal": offset_along_normal,
            "map_mode": map_mode,
            "if_exists": if_exists,
            },
            document_names=(doc_name,),
            operation_name="Create datum plane",
        )
        if raw_result is None:
            raw_result = make_create_datum_plane_uncertain(
                "CREATE_DATUM_PLANE_TRANSPORT_UNCERTAIN",
                "create_datum_plane response unavailable: JSON-RPC session is not connected",
                committed=None,
            )
    except Exception as exc:
        raw_result = make_create_datum_plane_uncertain(
            "CREATE_DATUM_PLANE_TRANSPORT_UNCERTAIN",
            f"CreateDatumPlane response unavailable: {exc}",
            committed=None,
        )
    result = parse_create_datum_plane_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            "Failed to create datum plane: " + result["error"],
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
