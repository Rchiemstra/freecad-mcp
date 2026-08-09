from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...responses.tool_results import tool_fail
from ...template_resources import render_template_lines
from .helpers import _doc_preamble, _run_json_code, _shared_helpers


def get_sketch_geometry_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    sketch_name: str,
    include_constraints: bool = True,
    include_external: bool = True,
    global_coords: bool = True,
) -> ToolResponse:
    lines = _doc_preamble(doc_name) + _shared_helpers() + render_template_lines(
        "p7_assembly/get_sketch_geometry.py.txt",
        sketch_name=repr(sketch_name),
        include_constraints=repr(include_constraints),
        include_external=repr(include_external),
        global_coords=repr(global_coords),
    )
    return _run_json_code(
        freecad,
        True,
        "\n".join(lines),
        "Failed to get sketch geometry",
        document=doc_name,
        read_only=True,
    )

def sketch_add_external_projection_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    source_ref: str,
    projection_mode: str = "auto",
    defining: bool = False,
    allow_gui_geometry_loop: bool = False,
) -> ToolResponse:
    if projection_mode not in {"auto", "edge", "face", "point"}:
        return tool_fail(
            "projection_mode must be one of: auto, edge, face, point",
            error_code="INVALID_ARGUMENT",
        )
    lines = _doc_preamble(doc_name) + _shared_helpers() + render_template_lines(
        "p7_assembly/sketch_add_external_projection.py.txt",
        sketch_name=repr(sketch_name),
        source_ref=repr(source_ref),
        projection_mode=repr(projection_mode),
        defining=repr(defining),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to add external projection",
        screenshot=True,
        document=doc_name,
        execution_mode="gui" if allow_gui_geometry_loop else "auto",
        allow_gui_geometry_loop=allow_gui_geometry_loop,
    )
