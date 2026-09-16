"""Unit tests for near-blank personal-view detection and ActiveView fallback."""

from __future__ import annotations

import struct
import zlib
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.collaboration_context_render import (
    render_personal_context_gui,
)
from addon.FreeCADMCP.rpc_server.view_manager_ops.screenshot_blank import is_near_blank_png
from addon.FreeCADMCP.rpc_server.view_manager_ops.screenshot import (
    capture_active_view_png_bytes,
)

pytestmark = pytest.mark.unit


def _png_bytes(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    color_type = 2
    raw = bytearray()
    for _ in range(height):
        raw.append(0)
        raw.extend(bytes(rgb) * width)
    compressed = zlib.compress(bytes(raw), level=9)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    chunks = [
        b"\x89PNG\r\n\x1a\n",
        struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr + b"\x00\x00\x00\x00",
        struct.pack(">I", len(compressed)) + b"IDAT" + compressed + b"\x00\x00\x00\x00",
        struct.pack(">I", 0) + b"IEND" + b"\x00\x00\x00\x00",
    ]
    return b"".join(chunks)


def _filtered_png_bytes(
    width: int, height: int, pixels: bytes, filter_type: int
) -> bytes:
    bpp = 3
    row_bytes = width * bpp
    raw = bytearray()
    previous = bytes(row_bytes)
    for row_index in range(height):
        row = pixels[row_index * row_bytes : (row_index + 1) * row_bytes]
        raw.append(filter_type)
        for index, value in enumerate(row):
            left = row[index - bpp] if index >= bpp else 0
            up = previous[index]
            up_left = previous[index - bpp] if index >= bpp else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = up
            elif filter_type == 3:
                predictor = (left + up) // 2
            else:
                estimate = left + up - up_left
                distances = (
                    abs(estimate - left),
                    abs(estimate - up),
                    abs(estimate - up_left),
                )
                predictor = (
                    left
                    if distances[0] <= distances[1] and distances[0] <= distances[2]
                    else (up if distances[1] <= distances[2] else up_left)
                )
            raw.append((value - predictor) & 0xFF)
        previous = row
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", len(ihdr))
        + b"IHDR"
        + ihdr
        + b"\x00\x00\x00\x00"
        + struct.pack(">I", len(zlib.compress(bytes(raw))))
        + b"IDAT"
        + zlib.compress(bytes(raw))
        + b"\x00\x00\x00\x00"
        + struct.pack(">I", 0)
        + b"IEND"
        + b"\x00\x00\x00\x00"
    )


@pytest.mark.parametrize("filter_type", range(5))
def test_is_near_blank_png_unfilters_all_standard_scanline_filters(filter_type):
    blank = _filtered_png_bytes(4, 4, bytes((40, 44, 48)) * 16, filter_type)
    varied = _filtered_png_bytes(
        4,
        4,
        bytes(
            channel
            for row in range(4)
            for column in range(4)
            for channel in (row * 40 + column * 10, 50, 100)
        ),
        filter_type,
    )

    assert is_near_blank_png(blank)
    assert not is_near_blank_png(varied)


@pytest.mark.parametrize(
    ("offset", "value"),
    [(24, 4), (25, 3), (28, 1)],
)
def test_is_near_blank_png_treats_unsupported_png_layouts_as_nonblank(offset, value):
    image = bytearray(_png_bytes(4, 4, (40, 44, 48)))
    image[offset] = value

    assert not is_near_blank_png(image)


def test_render_personal_context_keeps_filtered_nonblank_primary_capture(monkeypatch):
    content = _filtered_png_bytes(
        4,
        4,
        bytes(
            channel
            for row in range(4)
            for column in range(4)
            for channel in (row * 40 + column * 10, 50, 100)
        ),
        4,
    )
    document = SimpleNamespace(Name="Model", Label="Model", Objects=[])
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.collaboration_context_render.build_view_context",
        lambda *_args, **_kwargs: {"selection_paths": []},
    )
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.collaboration_context_render.render_temporary_context_gui",
        lambda *_args, **_kwargs: content,
    )
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.collaboration_context_render.capture_active_view_png_bytes",
        lambda **_kwargs: pytest.fail("filtered nonblank capture must not fall back"),
    )
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.collaboration_context_render.resolve_document",
        lambda *_args, **_kwargs: document,
    )

    image, context = render_personal_context_gui(
        SimpleNamespace(), actor="runtime", view_name="Isometric"
    )

    assert image == content
    assert "screenshot_fallback" not in context


def test_is_near_blank_png_detects_uniform_background():
    uniform = _png_bytes(8, 8, (40, 44, 48))
    varied = _png_bytes(8, 8, (10, 20, 30))
    varied_pixels = bytearray()
    for row in range(8):
        varied_pixels.append(0)
        for col in range(8):
            varied_pixels.extend((row * 30 + col * 5, 50, 100))
    varied_raw = zlib.compress(bytes(varied_pixels), level=9)
    ihdr = struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0)
    varied = (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr + b"\x00\x00\x00\x00"
        + struct.pack(">I", len(varied_raw)) + b"IDAT" + varied_raw + b"\x00\x00\x00\x00"
        + struct.pack(">I", 0) + b"IEND" + b"\x00\x00\x00\x00"
    )

    assert is_near_blank_png(uniform)
    assert not is_near_blank_png(varied)


def test_render_personal_context_gui_falls_back_to_active_view_save_image(monkeypatch):
    blank = _png_bytes(4, 4, (30, 30, 30))
    varied_pixels = bytearray()
    for row in range(4):
        varied_pixels.append(0)
        for col in range(4):
            varied_pixels.extend((row * 40 + col * 10, 50, 100))
    varied_raw = zlib.compress(bytes(varied_pixels), level=9)
    ihdr = struct.pack(">IIBBBBB", 4, 4, 8, 2, 0, 0, 0)
    content = (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr + b"\x00\x00\x00\x00"
        + struct.pack(">I", len(varied_raw)) + b"IDAT" + varied_raw + b"\x00\x00\x00\x00"
        + struct.pack(">I", 0) + b"IEND" + b"\x00\x00\x00\x00"
    )
    document = SimpleNamespace(Name="Model", Label="Model", Objects=[])

    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.collaboration_context_render.build_view_context",
        lambda *_args, **_kwargs: {"selection_paths": []},
    )
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.collaboration_context_render.render_temporary_context_gui",
        lambda *_args, **_kwargs: blank,
    )
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.collaboration_context_render.capture_active_view_png_bytes",
        lambda **_kwargs: (content, None),
    )
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.collaboration_context_render.resolve_document",
        lambda *_args, **_kwargs: document,
    )

    facade = SimpleNamespace()
    image, context = render_personal_context_gui(
        facade,
        actor="runtime",
        view_name="Isometric",
    )

    assert image == content
    assert context["screenshot_fallback"] == "active_view_save_image"


def test_capture_active_view_png_bytes_reads_saved_file(monkeypatch):
    expected = _png_bytes(2, 2, (90, 90, 90))

    def fake_save(path, **_kwargs):
        with open(path, "wb") as output:
            output.write(expected)
        return True

    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.view_manager_ops.screenshot.save_active_screenshot",
        fake_save,
    )
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.view_manager_ops.screenshot.tempfile.mktemp",
        lambda suffix: "/tmp/mcp-test-shot.png",
    )

    data, error = capture_active_view_png_bytes(view_name="Front")

    assert error is None
    assert data == expected
