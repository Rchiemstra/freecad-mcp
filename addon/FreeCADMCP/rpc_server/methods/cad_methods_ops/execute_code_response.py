"""execute_code GUI response shaping (Phase 4 slice 4F)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .execute_code_policy import flatten_recompute_errors


def finalize_gui_execute_response(
    annotate: Callable[[dict[str, Any]], dict[str, Any]],
    res: dict[str, Any],
    options: dict[str, Any],
) -> dict[str, Any]:
    if res.get("ok"):
        session = res.get("session", {})
        return annotate(
            {
                "success": True,
                "message": "Python code execution completed.\nOutput: "
                + res.get("stdout", ""),
                "recompute_errors": flatten_recompute_errors(session, options),
                "session": session,
                "structured": session,
                "execution": {"mode": "gui"},
            }
        )
    tb = res.get("traceback")
    return annotate(
        {
            "success": False,
            "error": res.get("error", "Unknown error"),
            "traceback": tb,
            "structured": tb,
            "session": res.get("session", {}),
            "message": res.get("stdout", ""),
            "is_error": True,
        }
    )
