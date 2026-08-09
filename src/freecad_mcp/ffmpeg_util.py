"""Resolve system ffmpeg and encode PNG frame sequences to MP4."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


FFMPEG_ENV = "FREECAD_MCP_FFMPEG"
_INSTALL_HINT = (
    "Install ffmpeg and ensure it is on PATH "
    "(e.g. winget install ffmpeg), or set FREECAD_MCP_FFMPEG to the binary."
)


class FFmpegNotFoundError(RuntimeError):
    pass


def resolve_ffmpeg() -> Path:
    """Return the ffmpeg executable from FREECAD_MCP_FFMPEG or PATH."""
    configured = os.environ.get(FFMPEG_ENV, "").strip()
    if configured:
        path = Path(configured)
        if path.is_file():
            return path.resolve()
        raise FFmpegNotFoundError(
            f"{FFMPEG_ENV}={configured!r} is not an existing file. {_INSTALL_HINT}"
        )
    found = shutil.which("ffmpeg")
    if found:
        return Path(found).resolve()
    raise FFmpegNotFoundError(f"ffmpeg not found. {_INSTALL_HINT}")


def encode_png_sequence_to_mp4(
    frame_dir: str | Path,
    output_path: str | Path,
    *,
    fps: float = 8.0,
    pattern: str = "frame_%03d.png",
    ffmpeg: str | Path | None = None,
) -> dict[str, Any]:
    """Encode ``frame_000.png``… under *frame_dir* into an H.264 MP4."""
    frame_root = Path(frame_dir)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    binary = Path(ffmpeg) if ffmpeg else resolve_ffmpeg()
    input_pattern = str(frame_root / pattern)
    command = [
        str(binary),
        "-y",
        "-framerate",
        str(float(fps)),
        "-i",
        input_pattern,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(out),
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not out.is_file():
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(
            f"ffmpeg failed (exit {completed.returncode}): {detail or 'no output'}"
        )
    frames = sorted(frame_root.glob(pattern.replace("%03d", "*")))
    return {
        "ok": True,
        "video_path": str(out.resolve()),
        "frame_count": len(frames),
        "fps": float(fps),
        "ffmpeg": str(binary),
        "command": command,
    }
