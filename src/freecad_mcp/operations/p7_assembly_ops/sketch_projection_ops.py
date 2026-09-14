from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...template_resources import render_template_lines
from .helpers import _doc_preamble, _run_json_code, _shared_helpers
from freecad_mcp.operations.parametric_ops.sketch_add_external_projection import (
    sketch_add_external_projection_operation,
)


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


__all__ = [
    "get_sketch_geometry_operation",
    "sketch_add_external_projection_operation",
]
