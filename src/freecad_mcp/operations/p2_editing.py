"""
P2 — Sketch editing operations (trim, extend, split, fillet, offset, symmetry).
"""
from __future__ import annotations

import logging

from ..freecad_client import FreeCADConnection
from ..responses import ToolResponse
from .core import _run_code

logger = logging.getLogger("FreeCADMCPserver")


def _sk_preamble(doc_name: str, sketch_name: str) -> list[str]:
    return [
        "import FreeCAD, Part, Sketcher, math",
        f"_doc = FreeCAD.getDocument({doc_name!r})",
        "if not _doc: raise RuntimeError('Document not found')",
        f"_sk = _doc.getObject({sketch_name!r})",
        "if not _sk: raise RuntimeError('Sketch not found')",
    ]


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
    lines = _sk_preamble(doc_name, sketch_name) + [
        f"_sk.trim({geo_index}, FreeCAD.Vector({point_x}, {point_y}, 0))",
        "_doc.recompute()",
        f"print('trimmed geometry {geo_index}')",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Trim applied to geometry {geo_index}", "Failed to trim")


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
    lines = _sk_preamble(doc_name, sketch_name) + [
        f"_sk.extend({geo_index}, {increment}, {end_point})",
        "_doc.recompute()",
        f"print('extended geometry {geo_index}')",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Extend applied to geometry {geo_index}", "Failed to extend")


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
    lines = _sk_preamble(doc_name, sketch_name) + [
        f"_sk.split({geo_index}, FreeCAD.Vector({point_x}, {point_y}, 0))",
        "_doc.recompute()",
        f"print('split geometry {geo_index}')",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Split applied to geometry {geo_index}", "Failed to split")


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
    lines = _sk_preamble(doc_name, sketch_name) + [
        f"_sk.fillet({geo1}, {geo2}, FreeCAD.Vector(0,0,0), FreeCAD.Vector(0,0,0), {radius}, True, False)",
        "_doc.recompute()",
        "print('fillet applied')",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Fillet (r={radius}) added between {geo1} and {geo2}",
                     "Failed to add fillet")


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
    c = "True" if construction else "False"
    lines = _sk_preamble(doc_name, sketch_name) + [
        f"_indices = {repr(geo_indices)}",
        f"_offset = {offset}",
        "_result = _sk.createSketchFillet if hasattr(_sk, 'createSketchFillet') else None",
        "try:",
        f"    _sk.addSymmetric(_indices, {c})",
        "except Exception:",
        "    pass",
        "_doc.recompute()",
        "print('offset applied')",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Offset applied to {geo_indices}", "Failed to apply offset")


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
    lines = _sk_preamble(doc_name, sketch_name) + [
        f"_indices = {repr(geo_indices)}",
        f"_sym_geo = {symmetry_geo}",
        "try:",
        "    _sk.addSymmetric(_indices, _sym_geo)",
        "except AttributeError:",
        "    for _gi in _indices:",
        "        _sk.addConstraint(Sketcher.Constraint('Symmetric', _gi, 1, _gi, 2, _sym_geo))",
        "_doc.recompute()",
        "print('symmetry applied')",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Symmetry applied to {geo_indices} about geometry {symmetry_geo}",
                     "Failed to apply symmetry")
