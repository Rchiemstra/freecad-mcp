"""Active-view orientation, sizing, and screenshot capture."""

from __future__ import annotations

# §3.3 compatibility shims — moved symbols keep their legacy import path.
from .view_manager_ops.animate_placement import animate_object_placement
from .view_manager_ops.orbit_frames import build_orbit_frames
from .view_manager_ops.placement_repair import repair_placements_and_refresh
from .view_manager_ops.refresh_view import refresh_active_view
from .view_manager_ops.screenshot import save_active_screenshot
from .view_manager_ops.view_constants import apply_view_orientation
from .view_manager_ops.view_sequence import save_view_sequence

__all__ = [
    "animate_object_placement",
    "apply_view_orientation",
    "build_orbit_frames",
    "refresh_active_view",
    "repair_placements_and_refresh",
    "save_active_screenshot",
    "save_view_sequence",
]
