"""Multi-frame screenshot capture."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .focus_helpers import normalize_focus_names
from .screenshot import save_active_screenshot


def save_view_sequence(
    frames: Sequence[dict[str, Any]],
    width: int | None = None,
    height: int | None = None,
) -> list[dict[str, Any]]:
    """Capture multiple framed screenshots.

    Each frame dict accepts:
    - ``view_name`` (default Isometric)
    - ``focus_object`` / ``focus_objects``
    - ``yaw_deg``
    - ``label``
    - ``path`` (required output PNG path)
    """
    results: list[dict[str, Any]] = []
    for index, frame in enumerate(frames):
        path = frame.get("path")
        if not path:
            results.append({"index": index, "ok": False, "error": "frame.path is required"})
            continue
        status = save_active_screenshot(
            str(path),
            view_name=str(frame.get("view_name") or "Isometric"),
            width=width if frame.get("width") is None else frame.get("width"),
            height=height if frame.get("height") is None else frame.get("height"),
            focus_object=frame.get("focus_object"),
            focus_objects=frame.get("focus_objects"),
            yaw_deg=frame.get("yaw_deg"),
        )
        results.append({
            "index": index,
            "ok": status is True,
            "error": None if status is True else str(status),
            "path": str(path),
            "label": frame.get("label") or f"frame_{index}",
            "view_name": frame.get("view_name") or "Isometric",
            "focus_objects": normalize_focus_names(
                frame.get("focus_object"), frame.get("focus_objects")
            ),
            "yaw_deg": frame.get("yaw_deg"),
        })
    return results
