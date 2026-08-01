from __future__ import annotations

import logging

from ...freecad_client import FreeCADConnection
from ...responses import ToolResponse, add_screenshot_if_available, json_response, tool_fail

logger = logging.getLogger("FreeCADMCPserver")

def run_fem_analysis_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    analysis_name: str,
    timeout: int = 600,
) -> ToolResponse:
    try:
        res = freecad.run_fem_analysis(doc_name, analysis_name, timeout)
        if res.get("success"):
            def fmt(v, unit):
                return f"{v:.4g} {unit}" if isinstance(v, (int, float)) else f"unavailable ({unit})"
            screenshot = freecad.get_active_screenshot() if not only_text_feedback else None
            response = json_response({
                "summary": (
                    f"FEM analysis '{analysis_name}' solved. "
                    f"max von Mises = {fmt(res.get('max_von_mises_MPa'), 'MPa')}, "
                    f"max displacement = {fmt(res.get('max_displacement_mm'), 'mm')} "
                    f"({res.get('node_count')} nodes)."
                ),
                **res,
            })
            return add_screenshot_if_available(response, screenshot, only_text_feedback)
        return json_response({
            "summary": f"FEM analysis '{analysis_name}' failed: {res.get('error')}",
            **res,
        })
    except Exception as e:
        logger.error(f"Failed to run FEM analysis: {e!s}")
        return tool_fail(
            f"Failed to run FEM analysis: {e!s}",
            error_code=type(e).__name__.upper(),
        )
