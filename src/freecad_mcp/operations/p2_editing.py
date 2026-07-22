"""
P2 — Sketch editing operations (trim, extend, split, fillet, offset, symmetry).
"""
from __future__ import annotations

import logging

from ..freecad_client import FreeCADConnection
from ..responses import ToolResponse
from ..template_resources import render_template_lines
from .core import _run_code

logger = logging.getLogger("FreeCADMCPserver")


def _sk_preamble(doc_name: str, sketch_name: str) -> list[str]:
    return render_template_lines(
        "p2_editing/sk_preamble.py.txt",
        doc_name=repr(doc_name),
        sketch_name=repr(sketch_name),
    )


# ---------------------------------------------------------------------------
# P2-1  sketch_trim
# ---------------------------------------------------------------------------

def sketch_trim_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    geo_index: int,
    point_x: float,
    point_y: float,
) -> ToolResponse:
    lines = _sk_preamble(doc_name, sketch_name) + render_template_lines(
        "p2_editing/sketch_trim.py.txt",
        geo_index=repr(geo_index),
        point_x=repr(point_x),
        point_y=repr(point_y),
        message=repr(f"trimmed geometry {geo_index}"),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Trim applied to geometry {geo_index}", "Failed to trim",
                     document=doc_name)


# ---------------------------------------------------------------------------
# P2-2  sketch_extend
# ---------------------------------------------------------------------------

def sketch_extend_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    geo_index: int,
    increment: float,
    end_point: int = 2,
) -> ToolResponse:
    lines = _sk_preamble(doc_name, sketch_name) + render_template_lines(
        "p2_editing/sketch_extend.py.txt",
        geo_index=repr(geo_index),
        increment=repr(increment),
        end_point=repr(end_point),
        message=repr(f"extended geometry {geo_index}"),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Extend applied to geometry {geo_index}", "Failed to extend",
                     document=doc_name)


# ---------------------------------------------------------------------------
# P2-3  sketch_split
# ---------------------------------------------------------------------------

def sketch_split_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    geo_index: int,
    point_x: float,
    point_y: float,
) -> ToolResponse:
    lines = _sk_preamble(doc_name, sketch_name) + render_template_lines(
        "p2_editing/sketch_split.py.txt",
        geo_index=repr(geo_index),
        point_x=repr(point_x),
        point_y=repr(point_y),
        message=repr(f"split geometry {geo_index}"),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Split applied to geometry {geo_index}", "Failed to split",
                     document=doc_name)


# ---------------------------------------------------------------------------
# P2-4  sketch_fillet
# ---------------------------------------------------------------------------

def sketch_fillet_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    geo1: int,
    geo2: int,
    radius: float,
) -> ToolResponse:
    if radius <= 0:
        from ..responses import text_response
        return text_response("fillet radius must be > 0")
    lines = _sk_preamble(doc_name, sketch_name) + render_template_lines(
        "p2_editing/sketch_fillet.py.txt",
        geo1=repr(geo1),
        geo2=repr(geo2),
        radius=repr(radius),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Fillet (r={radius}) added between {geo1} and {geo2}",
                     "Failed to add fillet", document=doc_name)


# ---------------------------------------------------------------------------
# P2-5  sketch_offset
# ---------------------------------------------------------------------------

def sketch_offset_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    geo_indices: list[int],
    offset: float,
    copy: bool = True,
    construction: bool = False,
) -> ToolResponse:
    lines = _sk_preamble(doc_name, sketch_name) + render_template_lines(
        "p2_editing/sketch_offset.py.txt",
        geo_indices=repr(geo_indices),
        offset=repr(offset),
        construction=repr(construction),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Offset applied to {geo_indices}", "Failed to apply offset",
                     document=doc_name)


# ---------------------------------------------------------------------------
# P2-6  sketch_symmetry
# ---------------------------------------------------------------------------

def sketch_symmetry_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    geo_indices: list[int],
    symmetry_geo: int,
    copy: bool = True,
) -> ToolResponse:
    lines = _sk_preamble(doc_name, sketch_name) + render_template_lines(
        "p2_editing/sketch_symmetry.py.txt",
        geo_indices=repr(geo_indices),
        symmetry_geo=repr(symmetry_geo),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Symmetry applied to {geo_indices} about geometry {symmetry_geo}",
                     "Failed to apply symmetry", document=doc_name)
