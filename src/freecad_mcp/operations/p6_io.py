"""
P6 — Import / export operations (STEP, STL, OBJ, DXF, BREP).
"""
from __future__ import annotations

import logging

from ..freecad_client import FreeCADConnection
from ..responses.constants import ToolResponse
from ..template_resources import render_template_lines
from .core import _run_code
from .parametric_ops.export_brep import export_brep_operation
from .parametric_ops.export_step import export_step_operation
from .parametric_ops.export_stl import export_stl_operation
from .parametric_ops.import_brep import import_brep_operation
from .parametric_ops.import_step import import_step_operation

logger = logging.getLogger("FreeCADMCPserver")


def _doc_preamble(doc_name: str) -> list[str]:
    return render_template_lines(
        "p6_io/doc_preamble.py.txt",
        doc_name=repr(doc_name),
        doc_missing=repr(f"Document {doc_name!r} not found"),
    )


# ---------------------------------------------------------------------------
# P6-6  apply_material / set_color
# ---------------------------------------------------------------------------

def set_color_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
    r: float,
    g: float,
    b: float,
    transparency: float = 0.0,
) -> ToolResponse:
    lines = _doc_preamble(doc_name) + render_template_lines(
        "p6_io/set_color.py.txt",
        obj_name=repr(obj_name),
        r=repr(r),
        g=repr(g),
        b=repr(b),
        transparency=repr(transparency),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Color applied to '{obj_name}'", "Failed to set color",
                     document=doc_name)


__all__ = [
    "export_brep_operation",
    "export_step_operation",
    "export_stl_operation",
    "import_brep_operation",
    "import_step_operation",
    "set_color_operation",
]
