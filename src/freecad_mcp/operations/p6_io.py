"""
P6 — Import / export operations (STEP, STL, OBJ, DXF, BREP).
"""
from __future__ import annotations

import logging

from ..freecad_client import FreeCADConnection
from ..responses import ToolResponse
from ..template_resources import render_template_lines
from .core import _run_code

logger = logging.getLogger("FreeCADMCPserver")


def _doc_preamble(doc_name: str) -> list[str]:
    return render_template_lines(
        "p6_io/doc_preamble.py.txt",
        doc_name=repr(doc_name),
        doc_missing=repr(f"Document {doc_name!r} not found"),
    )


# ---------------------------------------------------------------------------
# P6-1  export_step
# ---------------------------------------------------------------------------

def export_step_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    file_path: str,
    obj_names: list[str] | None = None,
) -> ToolResponse:
    lines = _doc_preamble(doc_name) + render_template_lines(
        "p6_io/export_step.py.txt",
        file_path=repr(file_path),
        obj_names=repr(obj_names) if obj_names else "None",
    )
    return _run_code(
        freecad,
        True,
        "\n".join(lines),
        f"Exported STEP to '{file_path}'",
        "Failed to export STEP",
        document=doc_name,
        recompute="none",
        capture_view=False,
        read_only=True,
        execution_mode="worker",
    )


# ---------------------------------------------------------------------------
# P6-2  import_step
# ---------------------------------------------------------------------------

def import_step_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    file_path: str,
) -> ToolResponse:
    lines = _doc_preamble(doc_name) + render_template_lines(
        "p6_io/import_step.py.txt",
        file_path=repr(file_path),
    )
    return _run_code(freecad, True, "\n".join(lines),
                     f"Imported STEP from '{file_path}'", "Failed to import STEP",
                     document=doc_name)


# ---------------------------------------------------------------------------
# P6-3  export_stl
# ---------------------------------------------------------------------------

def export_stl_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    file_path: str,
    obj_names: list[str] | None = None,
    mesh_deviation: float = 0.1,
) -> ToolResponse:
    lines = _doc_preamble(doc_name) + render_template_lines(
        "p6_io/export_stl.py.txt",
        file_path=repr(file_path),
        obj_names=repr(obj_names) if obj_names else "None",
        mesh_deviation=repr(mesh_deviation),
    )
    return _run_code(
        freecad,
        True,
        "\n".join(lines),
        f"Exported STL to '{file_path}'",
        "Failed to export STL",
        document=doc_name,
        recompute="none",
        capture_view=False,
        read_only=True,
        execution_mode="worker",
    )


# ---------------------------------------------------------------------------
# P6-4  export_brep
# ---------------------------------------------------------------------------

def export_brep_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    obj_name: str,
    file_path: str,
) -> ToolResponse:
    lines = _doc_preamble(doc_name) + render_template_lines(
        "p6_io/export_brep.py.txt",
        obj_name=repr(obj_name),
        file_path=repr(file_path),
    )
    return _run_code(
        freecad,
        True,
        "\n".join(lines),
        f"Exported BREP to '{file_path}'",
        "Failed to export BREP",
        document=doc_name,
        recompute="none",
        capture_view=False,
        read_only=True,
        execution_mode="worker",
    )


# ---------------------------------------------------------------------------
# P6-5  import_brep
# ---------------------------------------------------------------------------

def import_brep_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    file_path: str,
    obj_name: str = "BRepImport",
) -> ToolResponse:
    lines = _doc_preamble(doc_name) + render_template_lines(
        "p6_io/import_brep.py.txt",
        file_path=repr(file_path),
        obj_name=repr(obj_name),
    )
    return _run_code(freecad, True, "\n".join(lines),
                     f"Imported BREP from '{file_path}'", "Failed to import BREP",
                     document=doc_name)


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
