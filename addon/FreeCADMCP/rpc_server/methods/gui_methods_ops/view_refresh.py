"""Actor-scoped view refresh, placement repair, and animation RPC methods."""

from __future__ import annotations

import base64
import os
import tempfile
from typing import Any

from .collaboration_context import (
    encode_png_bytes,
    public_error,
    render_personal_view,
)
from .collaboration_context_core import collaborators, request_actor
from .collaboration_context_dispatch import dispatch_gui
from .collaboration_context_render import render_personal_context_gui

_MAX_ANIMATION_FRAMES = 120


def _validate_animation_frame_count(keyframes, path_object, sample_count):
    if keyframes:
        if not isinstance(keyframes, (list, tuple)):
            raise TypeError("keyframes must be a list")
        count = len(keyframes)
    elif path_object:
        count = max(2, int(sample_count))
    else:
        return
    if count > _MAX_ANIMATION_FRAMES:
        raise ValueError(
            f"placement animation exceeds maximum of {_MAX_ANIMATION_FRAMES} frames"
        )


def _focus_names(focus_objects: list[str] | None, fallback: str) -> list[str]:
    names = []
    for value in focus_objects or []:
        for item in str(value).split(","):
            item = item.strip()
            if item and item not in names:
                names.append(item)
    return names or [fallback]


def _animation_frame_gui(self, collabs, plan, sample, options, actor):
    collabs.apply_placement_sample(plan, sample)
    image, _ = render_personal_context_gui(
        self,
        actor=actor,
        hint=options["doc_name"],
        view_name=options["view_name"],
        focus_objects=options["focus_names"],
        fit=True,
        width=options["width"],
        height=options["height"],
    )
    return {
        "index": sample["index"],
        "ok": True,
        "error": None,
        "label": f"anim_{sample['index']:02d}",
        "position": [sample["x"], sample["y"], sample["z"]],
        "yaw_deg": sample["yaw_deg"],
        "image": image,
    }


def _animation_frames_gui(self, collabs, plan, options, actor):
    return [
        _animation_frame_gui(self, collabs, plan, sample, options, actor)
        for sample in plan["positions"]
    ]


def _run_placement_animation_gui(self, collabs, options, actor, animation_options):
    """Run the complete placement transaction in one GUI callback."""
    plan = None
    primary_error = None
    try:
        plan = collabs.prepare_placement_animation(**animation_options)
        return _animation_frames_gui(self, collabs, plan, options, actor)
    except BaseException as error:
        primary_error = error
        raise
    finally:
        if plan is not None:
            try:
                collabs.restore_placement_animation(plan)
            except BaseException as restore_error:
                if primary_error is not None:
                    primary_error.add_note(
                        f"placement restore also failed: {restore_error}"
                    )
                else:
                    raise


def _write_animation_frames(raw_frames, out_dir):
    frames = []
    for frame in raw_frames:
        path = os.path.join(out_dir, f"frame_{frame['index']:03d}.png")
        image = frame.pop("image")
        with open(path, "wb") as output:
            output.write(image)
        frames.append(
            {
                **frame,
                "path": path,
                "image_base64": base64.b64encode(image).decode("ascii"),
            }
        )
    return frames


def _finalize_animation_result(facade, raw_frames, focus_names):
    try:
        out_dir = tempfile.mkdtemp(prefix="mcp_anim_")
        frames = _write_animation_frames([dict(frame) for frame in raw_frames], out_dir)
    except Exception as exc:
        return public_error(facade, exc, frames=[])
    ok_count = sum(1 for frame in frames if frame["ok"])
    return {
        "ok": True,
        "frame_dir": out_dir,
        "frame_count": len(frames),
        "ok_count": ok_count,
        "restored": True,
        "frames": frames,
        "focus_objects": focus_names,
        "screenshot_ok": ok_count == len(frames) and bool(frames),
    }


def refresh_view(
    self,
    focus_objects: list[str] | None = None,
    focus_object: str | None = None,
    touch_objects: list[str] | None = None,
    fit: bool = False,
    capture: bool = False,
    view_name: str = "Isometric",
    width: int | None = None,
    height: int | None = None,
) -> dict[str, Any]:
    if touch_objects:
        return {
            "ok": False,
            "error_code": "PLACEMENT_REPAIR_REQUIRES_LEASE",
            "error": (
                "refresh_view is visual-only; use repair_view_placements "
                "with an explicit leased document"
            ),
        }
    try:
        image, context = render_personal_view(
            self,
            view_name=view_name,
            focus_object=focus_object,
            focus_objects=focus_objects,
            fit=fit,
            width=width,
            height=height,
        )
        result = {
            "ok": True,
            "touched": [],
            "focus_objects": context["selection_paths"],
            "framed": bool(fit or context["selection_paths"]),
        }
        if capture:
            result["image_base64"] = encode_png_bytes(image)
            if context.get("screenshot_fallback"):
                result["screenshot_fallback"] = context["screenshot_fallback"]
        return result
    except Exception as exc:
        return public_error(self, exc)


def repair_view_placements(
    self, doc_name: str, touch_objects: list[str], fit: bool = False
) -> dict[str, Any]:
    try:
        actor = request_actor(self)

        def repair_and_render():
            result = collaborators(self).repair_placements(doc_name, touch_objects)
            _, context = render_personal_context_gui(
                self,
                actor=actor,
                hint=doc_name,
                fit=fit,
            )
            result["focus_objects"] = context["selection_paths"]
            result["framed"] = bool(fit)
            return result

        return dispatch_gui(self, repair_and_render)
    except Exception as exc:
        return public_error(self, exc)


def animate_placement(
    self,
    doc_name: str,
    obj_name: str,
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
) -> dict[str, Any]:
    collabs = collaborators(self)
    actor = request_actor(self)
    names = _focus_names(focus_objects, obj_name)
    options = {
        "doc_name": doc_name,
        "view_name": view_name,
        "focus_names": names,
        "width": width,
        "height": height,
    }

    def finalize_result(raw_frames):
        return _finalize_animation_result(self, raw_frames, names)

    try:
        _validate_animation_frame_count(keyframes, path_object, sample_count)
        raw_frames = dispatch_gui(
            self,
            lambda: _run_placement_animation_gui(
                self,
                collabs,
                options,
                actor,
                {
                    "document_name": doc_name,
                    "object_name": obj_name,
                    "keyframes": keyframes,
                    "path_object": path_object,
                    "sample_count": sample_count,
                },
            ),
            late_result_transform=finalize_result,
        )
    except Exception as exc:
        return public_error(self, exc, frames=[])

    return finalize_result(raw_frames)


__all__ = ["animate_placement", "refresh_view", "repair_view_placements"]
