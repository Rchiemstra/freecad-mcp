from __future__ import annotations

from ...view_manager import save_active_screenshot as capture_active_screenshot

"""Internal screenshot helper for GUI methods."""


def save_active_screenshot(
    self,
    save_path: str,
    view_name: str | None = "Isometric",
    width: int | None = None,
    height: int | None = None,
    focus_object: str | None = None,
    focus_objects: list[str] | None = None,
    yaw_deg: float | None = None,
):
    return capture_active_screenshot(
        save_path,
        view_name or "Isometric",
        width,
        height,
        focus_object=focus_object,
        focus_objects=focus_objects,
        yaw_deg=yaw_deg,
    )
