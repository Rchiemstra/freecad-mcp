"""execute_code routing policy helpers (Phase 4 slice 4F)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def invalid_execution_mode_response(
    annotate: Callable[[dict[str, Any]], dict[str, Any]], execution_mode: str
) -> dict[str, Any]:
    return annotate(
        {
            "success": False,
            "is_error": True,
            "error_code": "invalid_execution_mode",
            "error": f"Unsupported execution_mode: {execution_mode!r}",
        }
    )


def worker_requires_read_only_response(
    annotate: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    return annotate(
        {
            "success": False,
            "is_error": True,
            "error_code": "invalid_execution_mode",
            "error": "execution_mode='worker' requires read_only=True",
        }
    )


def gui_timeout_not_supported_response(
    annotate: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    return annotate(
        {
            "success": False,
            "is_error": True,
            "error_code": "gui_timeout_not_supported",
            "error": (
                "timeout_seconds is a hard worker timeout and cannot safely "
                "stop code running on FreeCAD's GUI thread. Use read_only=true "
                "with execution_mode='auto' or 'worker', or remove "
                "timeout_seconds for bounded GUI work."
            ),
        }
    )


def _loop_block_guidance(
    *,
    block_worker_only_loop: bool,
    block_forced_gui_analysis: bool,
    block_forced_gui_loop: bool,
) -> str:
    if block_worker_only_loop:
        return (
            "Worker-only geometry loops cannot use the GUI override. "
            "Set read_only=true and execution_mode='worker' with a hard "
            "timeout so they run in an isolated FreeCADCmd process."
        )
    if block_forced_gui_analysis:
        return (
            "Read-only geometry loops cannot be forced onto the GUI thread. "
            "Use execution_mode='auto' or 'worker' so the analysis runs in "
            "an isolated FreeCADCmd process with a hard timeout."
        )
    if block_forced_gui_loop:
        return (
            "An expensive-geometry loop on the GUI thread cannot be "
            "interrupted and will freeze FreeCAD. For analysis, set "
            "read_only=true and execution_mode='worker' with a hard timeout. "
            "Only for a genuine bounded live-document mutation, pass "
            "allow_gui_geometry_loop=true and split the work into small chunks."
        )
    return (
        "For analysis, set read_only=true and execution_mode='worker' "
        "with a hard timeout. For an intentional document mutation, split "
        "the work into bounded chunks and explicitly set "
        "execution_mode='gui' with allow_gui_geometry_loop=true."
    )


def geometry_loop_block_response(
    annotate: Callable[[dict[str, Any]], dict[str, Any]],
    *,
    code: str,
    execution_mode: str,
    read_only: bool,
    allow_gui_loop: bool,
    find_gui_geometry_loop_risk_fn: Callable[[str], Any],
) -> dict[str, Any] | None:
    loop_risk = find_gui_geometry_loop_risk_fn(code)
    if loop_risk is None:
        return None
    block_unmarked_mutation = execution_mode == "auto" and not read_only
    block_forced_gui_analysis = execution_mode == "gui" and read_only
    block_forced_gui_loop = execution_mode == "gui" and not read_only and not allow_gui_loop
    block_worker_only_loop = loop_risk.worker_only_calls > 0
    if not (
        block_unmarked_mutation
        or block_forced_gui_analysis
        or block_forced_gui_loop
        or block_worker_only_loop
    ):
        return None
    guidance = _loop_block_guidance(
        block_worker_only_loop=block_worker_only_loop,
        block_forced_gui_analysis=block_forced_gui_analysis,
        block_forced_gui_loop=block_forced_gui_loop,
    )
    return annotate(
        {
            "success": False,
            "is_error": True,
            "blocked": "gui_thread_geometry_loop",
            "error": (
                "Blocked before execution: "
                f"{loop_risk.reason} ({loop_risk.expensive_calls} expensive "
                f"geometry call sites, {loop_risk.loops} loops). {guidance}"
            ),
        }
    )


def boolean_audit_block_response(
    annotate: Callable[[dict[str, Any]], dict[str, Any]],
    *,
    code: str,
    read_only: bool,
    find_gui_blocking_risk_fn: Callable[..., Any],
) -> dict[str, Any] | None:
    risk = find_gui_blocking_risk_fn(code, read_only=read_only)
    if risk is None:
        return None
    return annotate(
        {
            "success": False,
            "is_error": True,
            "blocked": "gui_thread_boolean_audit",
            "error": (
                "Blocked before execution: "
                f"{risk.reason} ({risk.boolean_calls} boolean calls, "
                f"{risk.transform_calls} transform calls). Use distToShape or "
                "sampled point-to-shape distances, or run the boolean audit in "
                "an isolated FreeCADCmd process."
            ),
        }
    )


def flatten_recompute_errors(session: dict, options: dict[str, Any]) -> list[dict]:
    flat_errors = []
    for key in (
        "target_recompute_errors",
        "pre_existing_target_errors",
        "unrelated_document_errors",
    ):
        for item in session.get(key, []):
            flat_errors.append(
                {
                    "doc": item.get("document") or options.get("document") or "?",
                    "name": item.get("object", "?"),
                    "state": item.get("state", []),
                }
            )
    return flat_errors
