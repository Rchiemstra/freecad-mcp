from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...template_resources import render_template_lines
from ..p7_assembly import _run_json_code
from ..parametric_ops.linear_pattern_feature import linear_pattern_feature_operation
from ..parametric_ops.mirror_feature import mirror_feature_operation
from ..parametric_ops.polar_pattern_feature import polar_pattern_feature_operation
from .code_gen import (
    _indented_build_assertion,
    _partdesign_bool_property_helper_code,
    _partdesign_extrusion_helper_code,
)
from .run_code import _run_code


def pad_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    pad_name: str,
    length: float,
    body_name: str | None = None,
    symmetric: bool = False,
    reversed_dir: bool = False,
    strict: bool = False,
) -> ToolResponse:
    lines = render_template_lines(
        "core/pad_feature.py.txt",
        doc_name=repr(doc_name),
        sketch_name=repr(sketch_name),
        body_name=repr(body_name),
        strict=repr(bool(strict)),
        pad_name=repr(pad_name),
        length=repr(length),
        extrusion_helpers="\n".join(_partdesign_extrusion_helper_code()),
        bool_helpers="\n".join(_partdesign_bool_property_helper_code()),
        symmetric=repr(symmetric),
        reversed_dir=repr(reversed_dir),
        verification=_indented_build_assertion(pad_name, sketch_name),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to create pad",
        screenshot=not only_text_feedback,
        document=doc_name,
    )

def pocket_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    pocket_name: str,
    length: float,
    body_name: str | None = None,
    symmetric: bool = False,
    reversed_dir: bool = False,
    strict: bool = False,
) -> ToolResponse:
    lines = render_template_lines(
        "core/pocket_feature.py.txt",
        doc_name=repr(doc_name),
        sketch_name=repr(sketch_name),
        body_name=repr(body_name),
        strict=repr(bool(strict)),
        pocket_name=repr(pocket_name),
        length=repr(length),
        extrusion_helpers="\n".join(_partdesign_extrusion_helper_code()),
        bool_helpers="\n".join(_partdesign_bool_property_helper_code()),
        symmetric=repr(symmetric),
        reversed_dir=repr(reversed_dir),
        verification=_indented_build_assertion(pocket_name, sketch_name),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to create pocket",
        screenshot=not only_text_feedback,
        document=doc_name,
    )

def create_spur_gear_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    gear_name: str,
    teeth: int,
    module: float,
    width: float,
    pressure_angle: float = 20.0,
    bore_diameter: float = 0.0,
    clearance: float = 0.0,
    backlash: float = 0.0,
    samples_per_flank: int = 8,
    body_name: str | None = None,
    sketch_name: str | None = None,
    tooth_profile: str = "involute",
) -> ToolResponse:
    lines = render_template_lines(
        "core/create_spur_gear.py.txt",
        doc_name=repr(doc_name),
        doc_missing=repr(f"Document {doc_name!r} not found"),
        gear_name=repr(gear_name),
        body_name=repr(body_name),
        sketch_name=repr(sketch_name),
        teeth=repr(teeth),
        module=repr(module),
        width=repr(width),
        pressure_angle=repr(pressure_angle),
        bore_diameter=repr(bore_diameter),
        clearance=repr(clearance),
        backlash=repr(backlash),
        samples_per_flank=repr(samples_per_flank),
        tooth_profile=repr(tooth_profile),
        extrusion_helpers="\n".join(_partdesign_extrusion_helper_code()),
        bool_helpers="\n".join(_partdesign_bool_property_helper_code()),
    )
    return _run_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        f"Spur gear '{gear_name}' sketch and pad created",
        "Failed to create spur gear",
        document=doc_name,
    )
