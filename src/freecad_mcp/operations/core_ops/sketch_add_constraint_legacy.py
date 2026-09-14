from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...template_resources import render_template_lines
from .code_gen import _constraint_line
from .run_code import _run_code


def sketch_add_constraint_legacy_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    constraints: list,
) -> ToolResponse:
    lines = render_template_lines(
        "core/sketch_add_constraint.py.txt",
        doc_name=repr(doc_name),
        sketch_name=repr(sketch_name),
        constraint_lines="\n".join(_constraint_line(c) for c in constraints),
        message=repr(f"{len(constraints)} constraint(s) added"),
    )
    return _run_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        f"Constraints added to '{sketch_name}'",
        "Failed to add constraints",
        document=doc_name,
    )
