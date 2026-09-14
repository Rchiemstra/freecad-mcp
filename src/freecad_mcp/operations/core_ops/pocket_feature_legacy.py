from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...template_resources import render_template_lines
from ..p7_assembly import _run_json_code
from .code_gen import (
    _indented_build_assertion,
    _partdesign_bool_property_helper_code,
    _partdesign_extrusion_helper_code,
)


def pocket_feature_legacy_operation(
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
