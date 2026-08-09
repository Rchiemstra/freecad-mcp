from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...template_resources import render_template_lines
from ..p7_assembly import _run_json_code
from .helpers import _doc_missing


def body_create_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    body_name: str,
) -> ToolResponse:
    lines = render_template_lines(
        "parametric/body_create.py.txt",
        doc_name=repr(doc_name),
        doc_missing=_doc_missing(doc_name),
        body_name=repr(body_name),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to create body",
        screenshot=False,
        document=doc_name,
    )

def body_set_tip_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    body_name: str,
    feature_name: str,
) -> ToolResponse:
    lines = render_template_lines(
        "parametric/body_set_tip.py.txt",
        doc_name=repr(doc_name),
        doc_missing=_doc_missing(doc_name),
        body_name=repr(body_name),
        feature_name=repr(feature_name),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to set body tip",
        screenshot=False,
        document=doc_name,
    )
