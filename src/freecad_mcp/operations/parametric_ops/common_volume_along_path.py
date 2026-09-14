from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.common_volume_along_path_contract import (
    CommonVolumeAlongPathRequest,
    make_common_volume_along_path_uncertain,
    parse_common_volume_along_path_response,
    DocumentName,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def common_volume_along_path_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    moving_object: str,
    obstacle_objects: list[str],
    *,
    path_object: str | None = None,
    sample_count: int = 12,
    samples: list[dict[str, object]] | None = None,
    volume_threshold_mm3: float = 1e-6,
    stop_on_first_hit: bool = False,
) -> CallToolResult:
    if not obstacle_objects:
        return tool_fail("obstacle_objects must contain at least one object name")
    if not samples and not path_object:
        return tool_fail("Provide samples (list of {x,y,z}) or path_object")
    request = CommonVolumeAlongPathRequest(
        doc_name=DocumentName(doc_name),
        moving_object=moving_object,
        obstacle_objects=obstacle_objects,
        path_object=path_object,
        sample_count=sample_count,
        samples=samples,
        volume_threshold_mm3=volume_threshold_mm3,
        stop_on_first_hit=stop_on_first_hit
    )
    try:
        raw_result: object = freecad.common_volume_along_path(doc_name, moving_object, obstacle_objects, path_object, sample_count, samples, volume_threshold_mm3, stop_on_first_hit)
    except Exception as exc:
        raw_result = make_common_volume_along_path_uncertain(
            "COMMON_VOLUME_ALONG_PATH_TRANSPORT_UNCERTAIN",
            f"CommonVolumeAlongPath response unavailable: {exc}",
            committed=None,
        )
    result = parse_common_volume_along_path_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run common_volume_along_path: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=True,
    )
