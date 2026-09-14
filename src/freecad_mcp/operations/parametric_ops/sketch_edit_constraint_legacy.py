from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...responses.tool_results import tool_fail
from ...template_resources import render_template_lines
from ..p7_assembly import _run_json_code
from .helpers import _doc_missing


def sketch_edit_constraint_legacy_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    value: float | None = None,
    name: str | None = None,
    index: int | None = None,
) -> ToolResponse:
    if name is None and index is None:
        return tool_fail(
            "Provide constraint name=... or index=... (prefer name after trim/fillet)"
        )
    lines = render_template_lines(
        "parametric/sketch_edit_constraint.py.txt",
        doc_name=repr(doc_name),
        doc_missing=_doc_missing(doc_name),
        sketch_name=repr(sketch_name),
        constraint_name=repr(name),
        constraint_index=repr(index),
        value=repr(value),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to edit constraint",
        screenshot=False,
        document=doc_name,
    )
