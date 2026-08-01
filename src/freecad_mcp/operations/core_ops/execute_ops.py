from __future__ import annotations

import logging

from ...execute_options import ExecuteOptions
from ...freecad_client import FreeCADConnection
from ...responses import ToolResponse, from_execute_result, tool_fail, tool_ok
from ...template_resources import render_template_lines

logger = logging.getLogger("FreeCADMCPserver")

def execute_code_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    code: str,
    document: str | None = None,
    recompute: str = "none",
    recompute_documents: list[str] | None = None,
    affected_documents: list[str] | None = None,
    read_only: bool = False,
    restore_active_document: bool = True,
    activate_document: bool = False,
    capture_view: bool = False,
    execution_mode: str = "auto",
    timeout_seconds: float | None = None,
    link_policy: str = "strict",
    allow_gui_geometry_loop: bool = False,
) -> ToolResponse:
    opts = ExecuteOptions(
        document=document,
        recompute=recompute,  # type: ignore[arg-type]
        recompute_documents=recompute_documents,
        affected_documents=affected_documents,
        read_only=read_only,
        restore_active_document=restore_active_document,
        activate_document=activate_document,
        capture_view=capture_view,
        execution_mode=execution_mode,  # type: ignore[arg-type]
        timeout_seconds=timeout_seconds,
        link_policy=link_policy,  # type: ignore[arg-type]
        allow_gui_geometry_loop=allow_gui_geometry_loop,
    )
    try:
        res = freecad.execute_code(code, opts)
        screenshot = (
            freecad.get_active_screenshot(view_name=None) if capture_view else None
        )
        if res["success"]:
            return from_execute_result(
                res,
                success_prefix="Code executed successfully",
                fail_prefix="Failed to execute code",
                screenshot=screenshot,
                only_text_feedback=only_text_feedback,
                capture_view=capture_view,
            )
        return from_execute_result(
            res,
            success_prefix="Code executed successfully",
            fail_prefix="Failed to execute code",
            screenshot=screenshot if capture_view else None,
            only_text_feedback=only_text_feedback,
            capture_view=False,
        )
    except Exception as e:
        logger.error(f"Failed to execute code: {e!s}")
        return tool_fail(f"Failed to execute code: {e!s}")

def execute_code_async_operation(
    freecad: FreeCADConnection,
    code: str,
) -> ToolResponse:
    try:
        res = freecad.execute_code_async(code)
        if res["success"]:
            return tool_ok(
                "Code execution started in background.\n"
                "Use get_object to poll a document object for completion "
                "(e.g. check SessionState.Label). "
                "FreeCAD's Report View will show output when done.",
                structured=res,
            )
        return tool_fail(
            f"Failed to start async execution: {res.get('error', 'unknown')}",
            structured=res,
            error_code=res.get("error_code"),
        )
    except Exception as e:
        logger.error(f"Failed to start async code execution: {e!s}")
        return tool_fail(
            f"Failed to start async code execution: {e!s}",
            error_code=type(e).__name__.upper(),
        )

def _get_view_geometry_fallback(
    freecad: FreeCADConnection,
    focus_object: str | None,
    focus_objects: list[str] | None,
) -> ToolResponse:
    focus_for_fallback = focus_object
    if not focus_for_fallback and focus_objects:
        focus_for_fallback = focus_objects[0]
    code = "\n".join(render_template_lines(
        "diagnostics/active_state.py.txt",
        focus_object=repr(focus_for_fallback),
    ))
    res = freecad.execute_code(
        code,
        ExecuteOptions(recompute="none", read_only=True, capture_view=False),
    )
    if not res.get("success"):
        raise RuntimeError("active_state fallback failed")
    output = res.get("message", "")
    marker = "Output:"
    if marker in output:
        output = output.split(marker, 1)[1].strip()
    note = (
        "Cannot get a viewable screenshot in the current view type "
        "(such as headless, TechDraw or Spreadsheet). Returning a "
        "compact geometric state instead; use capture_state / "
        "geometric_diff for richer text-only diffs, and find_faces / "
        "face_normal for specific subshapes."
    )
    return tool_ok(note + "\n" + output, structured=res)


def get_view_operation(
    freecad: FreeCADConnection,
    view_name: str,
    width: int | None = None,
    height: int | None = None,
    focus_object: str | None = None,
    focus_objects: list[str] | None = None,
    yaw_deg: float | None = None,
) -> ToolResponse:
    from ..interactive import normalize_view_name

    view_name = normalize_view_name(view_name)
    try:
        screenshot = freecad.get_active_screenshot(
            view_name,
            width,
            height,
            focus_object=focus_object,
            focus_objects=focus_objects,
            yaw_deg=yaw_deg,
        )
    except Exception as e:
        logger.error(f"Failed to get view: {e!s}")
        return tool_fail(f"Failed to get view: {e!s}")
    if screenshot is not None:
        focus_bits = []
        if focus_object:
            focus_bits.append(focus_object)
        if focus_objects:
            focus_bits.extend(focus_objects)
        label = f"View: {view_name}"
        if focus_bits:
            label += " | focus: " + ", ".join(focus_bits)
        if yaw_deg is not None:
            label += f" | yaw: {yaw_deg:g}°"
        return tool_ok(label, screenshot=screenshot)
    # P10 / I10 fallback: no viewable image (headless / TechDraw / Spreadsheet).
    # Return a compact geometric state of the focus object (or all objects) as a
    # text-only stand-in so the agent still gets something to reason about.
    try:
        return _get_view_geometry_fallback(freecad, focus_object, focus_objects)
    except Exception as e:
        logger.error(f"get_view fallback failed: {e}")
    return tool_fail(
        "Cannot get screenshot in the current view type "
        "(such as TechDraw or Spreadsheet)"
    )

def save_view_sequence_operation(
    freecad: FreeCADConnection,
    frames: list[dict] | None = None,
    width: int | None = None,
    height: int | None = None,
    orbit: dict | None = None,
    only_text_feedback: bool = False,
) -> ToolResponse:
    """Capture a multi-frame view sequence (manual frames and/or yaw orbit)."""
    result = freecad.capture_view_sequence(
        frames=frames,
        width=width,
        height=height,
        orbit=orbit,
    )
    if not result.get("ok"):
        return tool_fail(
            f"Failed to capture view sequence: {result.get('error', 'unknown error')}",
            structured=result if isinstance(result, dict) else None,
        )
    images = [
        frame.get("image_base64")
        for frame in result.get("frames", [])
        if frame.get("ok") and frame.get("image_base64")
    ]
    summary = {
        "ok": True,
        "frame_count": result.get("frame_count"),
        "ok_count": result.get("ok_count"),
        "frames": [
            {
                "index": frame.get("index"),
                "ok": frame.get("ok"),
                "label": frame.get("label"),
                "view_name": frame.get("view_name"),
                "focus_objects": frame.get("focus_objects"),
                "yaw_deg": frame.get("yaw_deg"),
                "error": frame.get("error"),
            }
            for frame in result.get("frames", [])
        ],
    }
    return tool_ok(
        f"Captured {result.get('ok_count', 0)}/{result.get('frame_count', 0)} view frames",
        screenshots=None if only_text_feedback else images,
        only_text_feedback=only_text_feedback,
        structured=summary,
    )
