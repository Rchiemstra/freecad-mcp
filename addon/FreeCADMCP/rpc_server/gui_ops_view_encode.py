"""View capture encoding helpers for GUI RPC methods."""

from __future__ import annotations

import base64
import contextlib
import os
from typing import Any


def encode_png_file(path: str) -> str:
    with open(path, "rb") as handle:
        return base64.b64encode(handle.read()).decode("utf-8")


def encode_view_sequence_frames(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    encoded_frames = []
    for item in results:
        payload = {
            "index": item["index"],
            "ok": item["ok"],
            "label": item.get("label"),
            "view_name": item.get("view_name"),
            "focus_objects": item.get("focus_objects") or [],
            "yaw_deg": item.get("yaw_deg"),
            "error": item.get("error"),
            "image_base64": None,
        }
        path = item.get("path")
        if item.get("ok") and path and os.path.exists(path):
            payload["image_base64"] = encode_png_file(path)
        encoded_frames.append(payload)
    return encoded_frames


def cleanup_temp_dir(tmp_dir: str) -> None:
    for name in os.listdir(tmp_dir):
        with contextlib.suppress(OSError):
            os.remove(os.path.join(tmp_dir, name))
    with contextlib.suppress(OSError):
        os.rmdir(tmp_dir)


__all__ = [
    "cleanup_temp_dir",
    "encode_png_file",
    "encode_view_sequence_frames",
]
