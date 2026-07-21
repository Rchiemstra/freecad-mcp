"""Unit tests for ffmpeg resolve/encode and video/anim MCP operations."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from mcp.types import ImageContent, TextContent

from freecad_mcp.ffmpeg_util import (
    FFmpegNotFoundError,
    encode_png_sequence_to_mp4,
    resolve_ffmpeg,
)
from freecad_mcp.operations.video_anim import (
    animate_placement_operation,
    encode_view_video_operation,
    refresh_view_operation,
)


def _text(response) -> str:
    content = response.content if hasattr(response, "content") else response
    return " ".join(item.text for item in content if isinstance(item, TextContent))


def test_resolve_ffmpeg_from_env(tmp_path, monkeypatch):
    binary = tmp_path / "ffmpeg.exe"
    binary.write_text("x", encoding="utf-8")
    monkeypatch.setenv("FREECAD_MCP_FFMPEG", str(binary))
    monkeypatch.setattr("freecad_mcp.ffmpeg_util.shutil.which", lambda _name: None)
    assert resolve_ffmpeg() == binary.resolve()


def test_resolve_ffmpeg_missing(monkeypatch):
    monkeypatch.delenv("FREECAD_MCP_FFMPEG", raising=False)
    monkeypatch.setattr("freecad_mcp.ffmpeg_util.shutil.which", lambda _name: None)
    with pytest.raises(FFmpegNotFoundError, match="ffmpeg not found"):
        resolve_ffmpeg()


def test_encode_png_sequence_argv(tmp_path, monkeypatch):
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_text("x", encoding="utf-8")
    frame_dir = tmp_path / "frames"
    frame_dir.mkdir()
    (frame_dir / "frame_000.png").write_bytes(b"png")
    (frame_dir / "frame_001.png").write_bytes(b"png")
    out = tmp_path / "out.mp4"
    seen = {}

    def _run(cmd, **kwargs):
        seen["cmd"] = cmd
        out.write_bytes(b"mp4")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("freecad_mcp.ffmpeg_util.subprocess.run", _run)
    result = encode_png_sequence_to_mp4(frame_dir, out, fps=12, ffmpeg=ffmpeg)
    assert result["ok"] is True
    assert result["frame_count"] == 2
    assert seen["cmd"][0] == str(ffmpeg)
    assert "-framerate" in seen["cmd"]
    assert "12.0" in seen["cmd"]
    assert "libx264" in seen["cmd"]
    assert str(out) in seen["cmd"]


def test_encode_view_video_fails_without_ffmpeg(monkeypatch):
    monkeypatch.delenv("FREECAD_MCP_FFMPEG", raising=False)
    monkeypatch.setattr("freecad_mcp.ffmpeg_util.shutil.which", lambda _name: None)
    conn = MagicMock()
    resp = encode_view_video_operation(conn, frame_paths=["a.png"])
    assert "ffmpeg" in _text(resp).lower()


def test_encode_view_video_from_frame_paths(tmp_path, monkeypatch):
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_text("x", encoding="utf-8")
    monkeypatch.setenv("FREECAD_MCP_FFMPEG", str(ffmpeg))
    src = tmp_path / "src"
    src.mkdir()
    p0 = src / "a.png"
    p1 = src / "b.png"
    p0.write_bytes(b"1")
    p1.write_bytes(b"2")

    def _run(cmd, **kwargs):
        Path(cmd[-1]).write_bytes(b"mp4")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("freecad_mcp.ffmpeg_util.subprocess.run", _run)
    conn = MagicMock()
    resp = encode_view_video_operation(
        conn, frame_paths=[str(p0), str(p1)], output_path=str(tmp_path / "clip.mp4"), fps=5
    )
    assert "Encoded" in _text(resp)
    assert resp.structuredContent["ok"] is True
    conn.capture_view_sequence_to_disk.assert_not_called()


def test_refresh_view_operation():
    conn = MagicMock()
    conn.refresh_view.return_value = {"ok": True, "touched": ["Link1"], "framed": True}
    resp = refresh_view_operation(conn, touch_objects=["Link1"], fit=True)
    assert "refreshed" in _text(resp).lower()
    conn.refresh_view.assert_called_once()


def test_animate_placement_operation_restores_and_optional_encode(tmp_path, monkeypatch):
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_text("x", encoding="utf-8")
    monkeypatch.setenv("FREECAD_MCP_FFMPEG", str(ffmpeg))
    frame_dir = tmp_path / "anim"
    frame_dir.mkdir()
    (frame_dir / "frame_000.png").write_bytes(b"png")

    def _run(cmd, **kwargs):
        Path(cmd[-1]).write_bytes(b"mp4")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("freecad_mcp.ffmpeg_util.subprocess.run", _run)
    conn = MagicMock()
    conn.animate_placement.return_value = {
        "ok": True,
        "frame_dir": str(frame_dir),
        "frame_count": 1,
        "ok_count": 1,
        "restored": True,
        "frames": [
            {
                "index": 0,
                "ok": True,
                "label": "anim_00",
                "position": [1, 2, 3],
                "image_base64": "img",
            }
        ],
    }
    resp = animate_placement_operation(
        conn,
        False,
        "Doc",
        "Box",
        keyframes=[{"x": 1, "y": 2, "z": 3}],
        encode_video=True,
        output_path=str(tmp_path / "anim.mp4"),
    )
    images = [
        item
        for item in (resp.content if hasattr(resp, "content") else resp)
        if isinstance(item, ImageContent)
    ]
    assert len(images) == 1
    assert resp.structuredContent["restored"] is True
    assert resp.structuredContent["video_path"]
