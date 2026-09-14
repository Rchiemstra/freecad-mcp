from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.create_helical_gear_contract import (
    CreateHelicalGearRequest,
    make_create_helical_gear_uncertain,
    parse_create_helical_gear_response,
    DocumentName,
    GearName,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def create_helical_gear_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    gear_name: str,
    teeth: int,
    module: float,
    width: float,
    helix_angle: float = 15.0,
    pressure_angle: float = 20.0,
    bore_diameter: float = 0.0,
    clearance: float = 0.0,
    backlash: float = 0.0,
    samples_per_flank: int = 12,
    body_name: str | None = None,
) -> CallToolResult:
    request = CreateHelicalGearRequest(
        doc_name=DocumentName(doc_name),
        gear_name=GearName(gear_name),
        teeth=teeth,
        module=module,
        width=width,
        helix_angle=helix_angle,
        pressure_angle=pressure_angle,
        bore_diameter=bore_diameter,
        clearance=clearance,
        backlash=backlash,
        samples_per_flank=samples_per_flank,
        body_name=body_name
    )
    try:
        raw_result: object = freecad.create_helical_gear(doc_name, gear_name, teeth, module, width, helix_angle, pressure_angle, bore_diameter, clearance, backlash, samples_per_flank, body_name)
    except Exception as exc:
        raw_result = make_create_helical_gear_uncertain(
            "CREATE_HELICAL_GEAR_TRANSPORT_UNCERTAIN",
            f"CreateHelicalGear response unavailable: {exc}",
            committed=None,
        )
    result = parse_create_helical_gear_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run create_helical_gear: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
