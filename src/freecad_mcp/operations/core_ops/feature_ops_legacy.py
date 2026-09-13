from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...template_resources import render_template_lines
from .code_gen import (
    _partdesign_bool_property_helper_code,
    _partdesign_pattern_helper_code,
)
from .run_code import _run_code


def linear_pattern_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    feature_name: str,
    pattern_name: str,
    length: float,
    occurrences: int,
    direction: str = "X_Axis",
    body_name: str | None = None,
    reversed_dir: bool = False,
) -> ToolResponse:
    lines = render_template_lines(
        "core/linear_pattern_feature.py.txt",
        doc_name=repr(doc_name),
        doc_missing=repr(f"Document {doc_name!r} not found"),
        feature_name=repr(feature_name),
        length=repr(length),
        occurrences=repr(occurrences),
        pattern_helpers="\n".join(_partdesign_pattern_helper_code()),
        bool_helpers="\n".join(_partdesign_bool_property_helper_code()),
        body_name=repr(body_name),
        pattern_name=repr(pattern_name),
        direction=repr(direction),
        reversed_dir=repr(reversed_dir),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Linear pattern '{pattern_name}' created", "Failed to create linear pattern",
                     document=doc_name)

def polar_pattern_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    feature_name: str,
    pattern_name: str,
    occurrences: int,
    angle: float = 360.0,
    axis: str = "Z_Axis",
    body_name: str | None = None,
    reversed_dir: bool = False,
) -> ToolResponse:
    lines = render_template_lines(
        "core/polar_pattern_feature.py.txt",
        doc_name=repr(doc_name),
        doc_missing=repr(f"Document {doc_name!r} not found"),
        feature_name=repr(feature_name),
        occurrences=repr(occurrences),
        angle=repr(angle),
        pattern_helpers="\n".join(_partdesign_pattern_helper_code()),
        bool_helpers="\n".join(_partdesign_bool_property_helper_code()),
        body_name=repr(body_name),
        pattern_name=repr(pattern_name),
        axis=repr(axis),
        reversed_dir=repr(reversed_dir),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Polar pattern '{pattern_name}' created", "Failed to create polar pattern",
                     document=doc_name)

def mirror_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    feature_name: str,
    mirror_name: str,
    plane: str = "YZ_Plane",
    body_name: str | None = None,
) -> ToolResponse:
    lines = render_template_lines(
        "core/mirror_feature.py.txt",
        doc_name=repr(doc_name),
        doc_missing=repr(f"Document {doc_name!r} not found"),
        feature_name=repr(feature_name),
        pattern_helpers="\n".join(_partdesign_pattern_helper_code()),
        body_name=repr(body_name),
        mirror_name=repr(mirror_name),
        plane=repr(plane),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Mirror feature '{mirror_name}' created", "Failed to create mirror feature",
                     document=doc_name)
