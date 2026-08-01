from __future__ import annotations

from typing import Any

from ...freecad_client import FreeCADConnection
from ...responses import ToolResponse
from ...template_resources import render_template_lines, render_template_text
from .helpers import _doc_preamble, _run_json_code, _shared_helpers, _validate_if_exists


def build_path_wire_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    wire_name: str,
    segments: list[dict[str, Any]],
    tolerance_mm: float = 0.5,
    container: str | None = None,
    if_exists: str = "error",
) -> ToolResponse:
    invalid = _validate_if_exists(if_exists)
    if invalid:
        return invalid
    lines = _doc_preamble(doc_name) + _shared_helpers() + render_template_lines(
        "p7_assembly/build_path_wire.py.txt",
        wire_name=repr(wire_name),
        segments=repr(segments),
        tolerance_mm=repr(tolerance_mm),
        container=repr(container),
        if_exists=repr(if_exists),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to build path wire",
        screenshot=True,
        document=doc_name,
    )

def sweep_pipe_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    path_wire: str,
    diameter_mm: float,
    solid_name: str,
    profile_mode: str = "frenet",
    color: list[float] | None = None,
    container: str | None = None,
    if_exists: str = "error",
) -> ToolResponse:
    invalid = _validate_if_exists(if_exists)
    if invalid:
        return invalid
    sweep_code = render_template_text(
        "p7_assembly/sweep_pipe.py.txt",
        path_wire_name=repr(path_wire),
        diameter=repr(diameter_mm),
        solid_name=repr(solid_name),
        profile_mode=repr(profile_mode),
        color=repr(color),
        container_name=repr(container),
        if_exists=repr(if_exists),
    )
    lines = [
        *_doc_preamble(doc_name),
        *_shared_helpers(),
        *sweep_code.strip().splitlines(),
    ]
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to sweep pipe",
        screenshot=True,
        document=doc_name,
    )
