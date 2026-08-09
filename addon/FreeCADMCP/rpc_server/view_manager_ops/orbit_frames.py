"""Orbit frame descriptor builders."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .focus_helpers import normalize_focus_names


def build_orbit_frames(
    *,
    focus_objects: Sequence[str] | None = None,
    focus_object: str | None = None,
    steps: int = 8,
    view_name: str = "Isometric",
    elevation_yaw_start_deg: float = 0.0,
) -> list[dict[str, Any]]:
    """Build yaw-orbit frame descriptors around the current focus."""
    names = normalize_focus_names(focus_object, focus_objects)
    count = max(2, int(steps))
    frames = []
    for i in range(count):
        yaw = elevation_yaw_start_deg + (360.0 * i / count)
        frames.append({
            "view_name": view_name,
            "focus_objects": names,
            "yaw_deg": yaw,
            "label": f"orbit_{i:02d}",
        })
    return frames
