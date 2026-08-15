from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...responses.tool_results import add_screenshot_if_available, tool_fail, tool_ok
from ...template_resources import render_template_lines
from .code_gen import (
    _partdesign_bool_property_helper_code,
    _partdesign_extrusion_helper_code,
    _partdesign_pattern_helper_code,
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
    return _typed_feature_response(
        freecad, only_text_feedback, "pad", doc_name, sketch_name, pad_name,
        length, body_name, symmetric, reversed_dir, strict,
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
    return _typed_feature_response(
        freecad, only_text_feedback, "pocket", doc_name, sketch_name, pocket_name,
        length, body_name, symmetric, reversed_dir, strict,
    )


def _typed_feature_response(
    freecad, only_text_feedback, kind, doc_name, sketch_name, feature_name,
    length, body_name, symmetric, reversed_dir, strict,
) -> ToolResponse:
    """Use the typed atomic RPC; feature templates are no longer public writes."""
    try:
        method = getattr(freecad, f"{kind}_feature")
        result = method(
            doc_name, sketch_name, feature_name, length, body_name, symmetric,
            reversed_dir, strict,
        )
    except Exception as exc:
        return tool_fail(f"Failed to create {kind}: {exc}")
    if not isinstance(result, dict) or result.get("success") is False or result.get("ok") is False:
        failure = result.get("error", result) if isinstance(result, dict) else result
        return tool_fail(
            f"Failed to create {kind}: {failure}",
            structured=result if isinstance(result, dict) else None,
            error_code=result.get("error_code") if isinstance(result, dict) else None,
        )
    screenshot = None
    if not only_text_feedback:
        try:
            screenshot = freecad.get_active_screenshot()
        except Exception as exc:
            # The model mutation has already committed.  Presentation capture
            # is best-effort and must never turn that success into a retryable
            # failure that could duplicate the feature.
            result = dict(result)
            result["presentation_warning"] = f"Screenshot capture failed: {exc}"
        if not screenshot:
            screenshot = None
            if "presentation_warning" not in result:
                # The generated connection method normalizes capture failures
                # to None, so absence must be handled just like a raised
                # exception. The typed mutation is already committed either
                # way.
                result = dict(result)
                result["presentation_warning"] = (
                    "Screenshot capture returned no image after the feature committed."
                )
    response = tool_ok(
        f"{kind.title()} '{result.get('feature', feature_name)}' created",
        structured=result,
        only_text_feedback=only_text_feedback,
    )
    return add_screenshot_if_available(response, screenshot, only_text_feedback)


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
