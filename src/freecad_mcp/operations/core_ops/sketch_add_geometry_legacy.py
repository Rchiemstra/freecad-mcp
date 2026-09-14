from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...template_resources import render_template_lines
from .code_gen import _geom_line
from .run_code import _run_code


def sketch_add_geometry_legacy_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    geometry: list,
) -> ToolResponse:
    lines = render_template_lines(
        "core/sketch_add_geometry.py.txt",
        doc_name=repr(doc_name),
        sketch_name=repr(sketch_name),
        geometry_lines="\n".join(_geom_line("", geom) for geom in geometry),
    )
    return _run_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        f"Geometry added to '{sketch_name}'",
        "Failed to add geometry",
        document=doc_name,
    )
