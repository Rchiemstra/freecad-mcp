"""MCP operations for video encode, placement animation, and view refresh."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from ..ffmpeg_util import FFmpegNotFoundError, encode_png_sequence_to_mp4, resolve_ffmpeg
from ..freecad_client import FreeCADConnection
from ..responses import ToolResponse, tool_fail, tool_ok

logger = logging.getLogger("FreeCADMCPserver")


def encode_view_video_operation(
    freecad: FreeCADConnection,
    *,
    frames: list[dict[str, Any]] | None = None,
    orbit: dict[str, Any] | None = None,
    frame_paths: list[str] | None = None,
    output_path: str | None = None,
    fps: float = 8.0,
    width: int | None = None,
    height: int | None = None,
    only_text_feedback: bool = False,
) -> ToolResponse:
    """Capture (optional) and encode a PNG sequence to MP4 via system ffmpeg."""
    try:
        ffmpeg = resolve_ffmpeg()
    except FFmpegNotFoundError as exc:
        return tool_fail(str(exc))

    work_dir: Path | None = None
    png_paths: list[Path] = []
    try:
        if frame_paths:
            png_paths = [Path(p) for p in frame_paths]
            missing = [str(p) for p in png_paths if not p.is_file()]
            if missing:
                return tool_fail(f"Missing frame files: {', '.join(missing[:5])}")
            work_dir = png_paths[0].parent
            # Re-number into sequential pattern if needed
            seq_dir = Path(tempfile.mkdtemp(prefix="mcp_video_frames_"))
            for index, src in enumerate(png_paths):
                dest = seq_dir / f"frame_{index:03d}.png"
                dest.write_bytes(src.read_bytes())
            work_dir = seq_dir
        else:
            if not frames and not orbit:
                return tool_fail("Provide frames, orbit, and/or frame_paths")
            capture = freecad.capture_view_sequence_to_disk(
                frames=frames,
                width=width,
                height=height,
                orbit=orbit,
            )
            if not capture.get("ok"):
                return tool_fail(
                    f"Failed to capture frames: {capture.get('error', 'unknown')}",
                    structured=capture if isinstance(capture, dict) else None,
                )
            work_dir = Path(capture["frame_dir"])
            png_paths = [Path(p) for p in capture.get("frame_paths", [])]

        if not png_paths and work_dir is not None:
            png_paths = sorted(work_dir.glob("frame_*.png"))
        if not png_paths:
            return tool_fail("No PNG frames available to encode")

        out = Path(output_path) if output_path else (work_dir / "view_sequence.mp4")
        encoded = encode_png_sequence_to_mp4(work_dir, out, fps=fps, ffmpeg=ffmpeg)
        return tool_ok(
            f"Encoded {encoded['frame_count']} frames to {encoded['video_path']}",
            only_text_feedback=only_text_feedback,
            structured=encoded,
        )
    except Exception as exc:
        logger.exception("encode_view_video failed")
        return tool_fail(f"Failed to encode view video: {exc}")


def refresh_view_operation(
    freecad: FreeCADConnection,
    *,
    focus_objects: list[str] | None = None,
    focus_object: str | None = None,
    touch_objects: list[str] | None = None,
    fit: bool = False,
    capture: bool = False,
    view_name: str = "Isometric",
    only_text_feedback: bool = False,
) -> ToolResponse:
    result = freecad.refresh_view(
        focus_objects=focus_objects,
        focus_object=focus_object,
        touch_objects=touch_objects,
        fit=fit,
        capture=capture,
        view_name=view_name,
    )
    if not result.get("ok"):
        return tool_fail(
            f"Failed to refresh view: {result.get('error', 'unknown')}",
            structured=result if isinstance(result, dict) else None,
        )
    screenshot = result.pop("image_base64", None) if capture else None
    response = tool_ok("View refreshed", structured=result)
    if capture and screenshot and not only_text_feedback:
        from ..responses import add_screenshot_if_available

        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    return response


def repair_view_placements_operation(
    freecad: FreeCADConnection,
    *,
    doc_name: str,
    touch_objects: list[str],
    fit: bool = False,
) -> ToolResponse:
    result = freecad.repair_view_placements(doc_name, touch_objects, fit)
    if not result.get("ok"):
        return tool_fail(
            f"Failed to repair placements: {result.get('error', 'unknown')}",
            structured=result,
        )
    return tool_ok("Placements repaired and view refreshed", structured=result)


def animate_placement_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
    *,
    keyframes: list[dict[str, Any]] | None = None,
    path_object: str | None = None,
    sample_count: int = 12,
    view_name: str = "Isometric",
    focus_objects: list[str] | None = None,
    width: int | None = None,
    height: int | None = None,
    encode_video: bool = False,
    fps: float = 8.0,
    output_path: str | None = None,
) -> ToolResponse:
    result = freecad.animate_placement(
        doc_name,
        obj_name,
        keyframes=keyframes,
        path_object=path_object,
        sample_count=sample_count,
        view_name=view_name,
        focus_objects=focus_objects,
        width=width,
        height=height,
    )
    if not result.get("ok"):
        return tool_fail(
            f"Failed to animate placement: {result.get('error', 'unknown')}",
            structured=result if isinstance(result, dict) else None,
        )
    video_path = None
    if encode_video:
        try:
            frame_dir = result.get("frame_dir")
            if not frame_dir:
                raise RuntimeError("animation result missing frame_dir")
            out = Path(output_path) if output_path else Path(frame_dir) / "placement_anim.mp4"
            encoded = encode_png_sequence_to_mp4(frame_dir, out, fps=float(fps))
            video_path = encoded["video_path"]
            result["video_path"] = video_path
        except Exception as exc:
            return tool_fail(
                f"Placement animation captured but video encode failed: {exc}",
                structured=result if isinstance(result, dict) else None,
            )
    images = [
        frame.get("image_base64")
        for frame in result.get("frames", [])
        if frame.get("ok") and frame.get("image_base64")
    ]
    summary = {
        "ok": True,
        "doc_name": doc_name,
        "obj_name": obj_name,
        "frame_count": result.get("frame_count"),
        "ok_count": result.get("ok_count"),
        "restored": result.get("restored"),
        "video_path": video_path,
        "frame_dir": result.get("frame_dir"),
        "frames": [
            {
                "index": frame.get("index"),
                "ok": frame.get("ok"),
                "label": frame.get("label"),
                "position": frame.get("position"),
                "error": frame.get("error"),
            }
            for frame in result.get("frames", [])
        ],
    }
    return tool_ok(
        f"Animated {result.get('ok_count', 0)}/{result.get('frame_count', 0)} placement frames"
        + (f"; video={video_path}" if video_path else ""),
        screenshots=None if only_text_feedback else images,
        only_text_feedback=only_text_feedback,
        structured=summary,
    )
