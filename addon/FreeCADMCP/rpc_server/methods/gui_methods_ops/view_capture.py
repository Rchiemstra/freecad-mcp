"""Actor-scoped screenshot and view-sequence RPC methods."""

from __future__ import annotations

import os
import tempfile
from typing import Any

from .collaboration_context import (
    GuiDispatchFailure,
    encode_png_bytes,
    public_error,
    redacted_error,
    render_personal_view,
)

_MAX_SEQUENCE_FRAMES = 120


def get_active_screenshot(
    self,
    view_name: str | None = "Isometric",
    width: int | None = None,
    height: int | None = None,
    focus_object: str | None = None,
    focus_objects: list[str] | None = None,
    yaw_deg: float | None = None,
) -> str:
    """Get a base64 PNG rendered from this requester's personal view context."""

    try:
        image, _ = render_personal_view(
            self,
            view_name=view_name or "Isometric",
            width=width,
            height=height,
            focus_object=focus_object,
            focus_objects=focus_objects,
            yaw_deg=yaw_deg,
            fit=True,
        )
        return encode_png_bytes(image)
    except GuiDispatchFailure:
        raise
    except Exception as exc:
        redacted_error(self, exc)
        return None


def _sequence_specs(
    frames: list[dict[str, Any]] | None, orbit: dict[str, Any] | None
) -> list[dict[str, Any]]:
    if frames is not None and not isinstance(frames, (list, tuple)):
        raise TypeError("frames must be a list")
    specs: list[dict[str, Any]] = []
    if orbit:
        if not isinstance(orbit, dict):
            raise TypeError("orbit must be a dict")
        steps = max(2, int(orbit.get("steps") or 8))
        if steps > _MAX_SEQUENCE_FRAMES:
            raise ValueError(
                f"view sequence exceeds maximum of {_MAX_SEQUENCE_FRAMES} frames"
            )
        start = float(orbit.get("yaw_start_deg") or 0.0)
        specs.extend(
            {
                "view_name": str(orbit.get("view_name") or "Isometric"),
                "focus_object": orbit.get("focus_object"),
                "focus_objects": orbit.get("focus_objects"),
                "yaw_deg": start + (360.0 * index / steps),
                "label": f"orbit_{index:02d}",
            }
            for index in range(steps)
        )
    if len(frames or ()) + len(specs) > _MAX_SEQUENCE_FRAMES:
        raise ValueError(
            f"view sequence exceeds maximum of {_MAX_SEQUENCE_FRAMES} frames"
        )
    specs.extend(dict(frame) for frame in (frames or []))
    return specs


def _capture_frame(
    self, frame: dict[str, Any], width: int | None, height: int | None
) -> tuple[bytes, dict[str, Any]]:
    return render_personal_view(
        self,
        hint=frame.get("document")
        or frame.get("doc_name")
        or frame.get("document_name"),
        view_name=frame.get("view_name") or "Isometric",
        width=width if frame.get("width") is None else frame.get("width"),
        height=height if frame.get("height") is None else frame.get("height"),
        focus_object=frame.get("focus_object"),
        focus_objects=frame.get("focus_objects"),
        yaw_deg=frame.get("yaw_deg"),
        fit=True if frame.get("fit") is None else bool(frame.get("fit")),
    )


def capture_view_sequence(
    self,
    frames: list[dict[str, Any]] | None = None,
    width: int | None = None,
    height: int | None = None,
    orbit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Capture multiple frames as in-memory, base64-encoded PNG payloads."""

    try:
        specs = _sequence_specs(frames, orbit)
    except Exception as exc:
        return public_error(self, exc, frames=[])
    if not specs:
        return {"ok": False, "error": "Provide frames and/or orbit", "frames": []}
    results = []
    for index, frame in enumerate(specs):
        try:
            image, context = _capture_frame(self, frame, width, height)
            results.append(
                {
                    "ok": True,
                    "index": index,
                    "label": frame.get("label") or f"frame_{index}",
                    "view_name": frame.get("view_name") or "Isometric",
                    "focus_objects": context["selection_paths"],
                    "yaw_deg": frame.get("yaw_deg"),
                    "error": None,
                    "image_base64": encode_png_bytes(image),
                }
            )
        except GuiDispatchFailure as exc:
            return public_error(self, exc, frames=results)
        except Exception as exc:
            results.append(
                {
                    "ok": False,
                    "index": index,
                    "label": frame.get("label") or f"frame_{index}",
                    "view_name": frame.get("view_name") or "Isometric",
                    "focus_objects": frame.get("focus_objects") or [],
                    "yaw_deg": frame.get("yaw_deg"),
                    "error": redacted_error(self, exc),
                    "image_base64": None,
                }
            )
    ok_count = sum(1 for frame in results if frame["ok"])
    return {
        "ok": bool(ok_count),
        "frame_count": len(results),
        "ok_count": ok_count,
        "frames": results,
    }


def capture_view_sequence_to_disk(
    self,
    frames: list[dict[str, Any]] | None = None,
    width: int | None = None,
    height: int | None = None,
    orbit: dict[str, Any] | None = None,
    frame_dir: str | None = None,
) -> dict[str, Any]:
    """Render personal-view frames and write the returned PNG bytes to disk."""

    try:
        specs = _sequence_specs(frames, orbit)
    except Exception as exc:
        return public_error(self, exc, frame_paths=[])
    if not specs:
        return {"ok": False, "error": "Provide frames and/or orbit", "frame_paths": []}
    try:
        out_dir = frame_dir or tempfile.mkdtemp(prefix="mcp_view_disk_")
        os.makedirs(out_dir, exist_ok=True)
    except Exception as exc:
        return public_error(self, exc, frame_paths=[], frames=[], frame_dir=None)
    results, paths = [], []
    for index, frame in enumerate(specs):
        path = os.path.join(out_dir, f"frame_{index:03d}.png")
        try:
            image, context = _capture_frame(self, frame, width, height)
            with open(path, "wb") as output:
                output.write(image)
            results.append(
                {
                    "ok": True,
                    "index": index,
                    "path": path,
                    "label": frame.get("label") or f"frame_{index}",
                    "view_name": frame.get("view_name") or "Isometric",
                    "focus_objects": context["selection_paths"],
                    "yaw_deg": frame.get("yaw_deg"),
                    "error": None,
                }
            )
            paths.append(path)
        except GuiDispatchFailure as exc:
            return public_error(self, exc, frame_paths=paths, frames=results)
        except Exception as exc:
            results.append(
                {
                    "ok": False,
                    "index": index,
                    "path": path,
                    "label": frame.get("label") or f"frame_{index}",
                    "view_name": frame.get("view_name") or "Isometric",
                    "focus_objects": frame.get("focus_objects") or [],
                    "yaw_deg": frame.get("yaw_deg"),
                    "error": redacted_error(self, exc),
                }
            )
    return {
        "ok": bool(paths),
        "frame_dir": out_dir,
        "frame_count": len(results),
        "ok_count": len(paths),
        "frame_paths": paths,
        "frames": results,
    }


__all__ = [
    "capture_view_sequence",
    "capture_view_sequence_to_disk",
    "get_active_screenshot",
]
