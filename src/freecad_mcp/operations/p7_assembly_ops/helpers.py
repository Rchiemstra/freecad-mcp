from __future__ import annotations

import json
import logging

from ...execute_options import ExecuteOptions
from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...responses.tool_results import add_screenshot_if_available, tool_fail, tool_ok
from ...template_resources import render_template_lines

logger = logging.getLogger("FreeCADMCPserver")

_PREFLIGHT_SENTINEL = "__PREFLIGHT_WARN__"


def _extract_execute_output(message: str) -> str:
    marker = "Output:"
    if marker in message:
        return message.split(marker, 1)[1].strip()
    return message.strip()

def _extract_preflight(output: str) -> tuple[str, str]:
    """I6 — pull the `__PREFLIGHT_WARN__` sentinel out of the execute output.

    Returns (clean_output, warning_text). The clean_output is the original JSON
    payload with the sentinel line removed (so JSON callers stay happy); the
    warning_text is a human-readable block surfaced to the agent when a
    cross-body attachment risk was detected at creation time (P1).
    """
    idx = output.rfind(_PREFLIGHT_SENTINEL)
    if idx < 0:
        return output, ""
    payload = output[idx + len(_PREFLIGHT_SENTINEL):]
    payload = payload.strip().splitlines()[0] if payload.strip() else ""
    clean = output[:idx].rstrip()
    try:
        warns = json.loads(payload) if payload else []
    except Exception:
        warns = []
    if not warns:
        return clean, ""
    lines = []
    for w in warns:
        lines.append(
            f"PREFLIGHT WARNING ({w.get('datum','?')}): {w.get('message','?')}"
        )
    return clean, "\n".join(lines)

def _run_json_code(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    code: str,
    fail_prefix: str,
    *,
    screenshot: bool = False,
    document: str | None = None,
    read_only: bool = False,
    execution_mode: str = "auto",
    allow_gui_geometry_loop: bool = False,
) -> ToolResponse:
    try:
        opts = ExecuteOptions(
            document=document,
            affected_documents=[document] if document and not read_only else None,
            recompute="none" if read_only else "target",
            recompute_documents=[document] if document and not read_only else None,
            read_only=read_only,
            execution_mode="worker" if read_only else execution_mode,
            restore_active_document=True,
            capture_view=screenshot,
            allow_gui_geometry_loop=allow_gui_geometry_loop,
            generated_operation=True,
            operation_id=fail_prefix,
        )
        res = freecad.execute_code(code, opts)
        image = freecad.get_active_screenshot() if screenshot else None
        if res.get("success"):
            output = _extract_execute_output(res.get("message", ""))
            output, preflight = _extract_preflight(output)
            errors = res.get("recompute_errors", [])
            if errors and output.endswith("}"):
                output += "\n" + str({"recompute_errors": errors})
            if preflight:
                output = output + "\n" + preflight
            return add_screenshot_if_available(
                tool_ok(output, structured=res),
                image,
                only_text_feedback,
            )
        return tool_fail(
            f"{fail_prefix}: {res.get('error', res.get('message', 'unknown error'))}",
            structured=res,
            error_code=res.get("error_code"),
        )
    except Exception as exc:
        logger.error("%s: %s", fail_prefix, exc)
        return tool_fail(f"{fail_prefix}: {exc}")

def _validate_if_exists(if_exists: str) -> ToolResponse | None:
    if if_exists not in {"error", "skip", "replace"}:
        return tool_fail(
            "if_exists must be one of: error, skip, replace",
            error_code="INVALID_ARGUMENT",
        )
    return None

def _doc_preamble(doc_name: str) -> list[str]:
    return render_template_lines(
        "p7_assembly/doc_preamble.py.txt",
        doc_name=repr(doc_name),
        doc_missing=repr(f"Document {doc_name!r} not found"),
    )

def _shared_helpers() -> list[str]:
    return render_template_lines("p7_assembly/shared_helpers.py.txt")
