from __future__ import annotations

import logging

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...template_resources import render_template_lines
from .code_gen import _constraint_line
from .run_code import _run_code

logger = logging.getLogger("FreeCADMCPserver")

def sketch_add_line_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str,
    x1: float, y1: float, x2: float, y2: float,
    construction: bool = False,
) -> ToolResponse:
    lines = render_template_lines(
        "core/sketch_add_line.py.txt",
        doc_name=repr(doc_name),
        sketch_name=repr(sketch_name),
        x1=repr(x1),
        y1=repr(y1),
        x2=repr(x2),
        y2=repr(y2),
        construction=repr(construction),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Line added to '{sketch_name}'", "Failed to add line",
                     document=doc_name)

def sketch_add_circle_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str,
    cx: float, cy: float, radius: float,
    construction: bool = False,
) -> ToolResponse:
    lines = render_template_lines(
        "core/sketch_add_circle.py.txt",
        doc_name=repr(doc_name),
        sketch_name=repr(sketch_name),
        cx=repr(cx),
        cy=repr(cy),
        radius=repr(radius),
        construction=repr(construction),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Circle added to '{sketch_name}'", "Failed to add circle",
                     document=doc_name)

def sketch_add_arc_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str,
    cx: float, cy: float, radius: float,
    start_angle: float, end_angle: float,
    construction: bool = False,
) -> ToolResponse:
    lines = render_template_lines(
        "core/sketch_add_arc.py.txt",
        doc_name=repr(doc_name),
        sketch_name=repr(sketch_name),
        cx=repr(cx),
        cy=repr(cy),
        radius=repr(radius),
        start_angle=repr(start_angle),
        end_angle=repr(end_angle),
        construction=repr(construction),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Arc added to '{sketch_name}'", "Failed to add arc",
                     document=doc_name)

def sketch_add_rectangle_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str,
    x1: float, y1: float, x2: float, y2: float,
    construction: bool = False,
) -> ToolResponse:
    lines = render_template_lines(
        "core/sketch_add_rectangle.py.txt",
        doc_name=repr(doc_name),
        sketch_name=repr(sketch_name),
        x1=repr(x1),
        y1=repr(y1),
        x2=repr(x2),
        y2=repr(y2),
        construction=repr(construction),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Rectangle added to '{sketch_name}'", "Failed to add rectangle",
                     document=doc_name)

def _run_constraint(freecad, only_text_feedback, doc_name, sketch_name, c_dict):
    lines = render_template_lines(
        "core/run_constraint.py.txt",
        doc_name=repr(doc_name),
        sketch_name=repr(sketch_name),
        constraint_line=_constraint_line(c_dict),
        message=repr(c_dict["type"] + " constraint added"),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"{c_dict['type']} constraint added to '{sketch_name}'",
                     "Failed to add constraint", document=doc_name)

def sketch_constrain_coincident_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str,
    geo1: int, pos1: int, geo2: int, pos2: int,
) -> ToolResponse:
    return _run_constraint(
        freecad,
        only_text_feedback,
        doc_name,
        sketch_name,
        {
            "type": "Coincident",
            "geo1": geo1,
            "pos1": pos1,
            "geo2": geo2,
            "pos2": pos2,
        },
    )

def sketch_constrain_horizontal_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str, geo: int,
) -> ToolResponse:
    return _run_constraint(freecad, only_text_feedback, doc_name, sketch_name,
                           {"type": "Horizontal", "geo": geo})

def sketch_constrain_vertical_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str, geo: int,
) -> ToolResponse:
    return _run_constraint(freecad, only_text_feedback, doc_name, sketch_name,
                           {"type": "Vertical", "geo": geo})

def sketch_constrain_distance_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str,
    geo: int, value: float, pos: int | None = None,
    name: str | None = None,
) -> ToolResponse:
    c: dict = {"type": "Distance", "geo": geo, "value": value}
    if pos is not None:
        c["pos"] = pos
    if name:
        c["name"] = name
    return _run_constraint(freecad, only_text_feedback, doc_name, sketch_name, c)

def sketch_constrain_radius_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str, geo: int, value: float,
    name: str | None = None,
) -> ToolResponse:
    c: dict = {"type": "Radius", "geo": geo, "value": value}
    if name:
        c["name"] = name
    return _run_constraint(freecad, only_text_feedback, doc_name, sketch_name, c)

def sketch_constrain_equal_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str, geo1: int, geo2: int,
) -> ToolResponse:
    return _run_constraint(freecad, only_text_feedback, doc_name, sketch_name,
                           {"type": "Equal", "geo1": geo1, "geo2": geo2})

def sketch_constrain_parallel_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str, geo1: int, geo2: int,
) -> ToolResponse:
    return _run_constraint(freecad, only_text_feedback, doc_name, sketch_name,
                           {"type": "Parallel", "geo1": geo1, "geo2": geo2})

def sketch_constrain_perpendicular_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str, geo1: int, geo2: int,
) -> ToolResponse:
    return _run_constraint(freecad, only_text_feedback, doc_name, sketch_name,
                           {"type": "Perpendicular", "geo1": geo1, "geo2": geo2})

def sketch_constrain_tangent_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str, geo1: int, geo2: int,
) -> ToolResponse:
    return _run_constraint(freecad, only_text_feedback, doc_name, sketch_name,
                           {"type": "Tangent", "geo1": geo1, "geo2": geo2})
