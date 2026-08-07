from __future__ import annotations

import logging

from ...execute_options import ExecuteOptions
from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...responses.tool_results import add_screenshot_if_available, tool_fail, tool_ok
from ...template_resources import render_template_lines
from .recompute_log import _format_recompute_log

logger = logging.getLogger("FreeCADMCPserver")

def _run_code(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    code: str,
    success_msg: str,
    fail_prefix: str,
    *,
    document: str | None = None,
    recompute: str = "target",
    capture_view: bool = True,
    read_only: bool = False,
    execution_mode: str = "auto",
) -> ToolResponse:
    """Execute generated Python code in FreeCAD and return a formatted response."""
    try:
        effective_recompute = "none" if read_only else recompute
        full_code = code + "\n" + "\n".join(
            render_template_lines("diagnostics/recompute_log.py.txt")
        )
        opts = ExecuteOptions(
            document=document,
            affected_documents=[document] if document and not read_only else None,
            recompute=effective_recompute,  # type: ignore[arg-type]
            recompute_documents=(
                [document] if document and effective_recompute == "target" else None
            ),
            capture_view=capture_view,
            read_only=read_only,
            execution_mode=(
                "worker" if read_only and execution_mode == "auto" else execution_mode
            ),  # type: ignore[arg-type]
            generated_operation=True,
            operation_id=success_msg,
        )
        res = freecad.execute_code(full_code, opts)
        screenshot = freecad.get_active_screenshot() if capture_view else None
        if res["success"]:
            output = res.get("message", "")
            msg = f"{success_msg}\n{output}".strip()
            log_summary = _format_recompute_log(output)
            if log_summary:
                msg += f"\n{log_summary}"
            errors = res.get("recompute_errors", [])
            if errors and not log_summary:
                names = ", ".join(
                    f"{e['name']} (doc={e.get('doc','?')}, state={e['state']})"
                    for e in errors
                )
                msg += f"\nRecompute errors detected: {names}"
            response = tool_ok(msg, structured=res)
        else:
            response = tool_fail(
                f"{fail_prefix}: {res.get('error', res.get('message', 'unknown error'))}",
                structured=res,
                error_code=res.get("error_code"),
            )
        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    except Exception as e:
        logger.error(f"{fail_prefix}: {e}")
        return tool_fail(f"{fail_prefix}: {e}")
