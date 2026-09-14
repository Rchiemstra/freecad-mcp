from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...template_resources import render_template_lines
from ..p7_assembly import _run_json_code
from .clear_expression import clear_expression_operation
from .helpers import _doc_missing
from .set_expression import set_expression_operation


def list_expressions_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    object_name: str,
) -> ToolResponse:
    lines = render_template_lines(
        "parametric/list_expressions.py.txt",
        doc_name=repr(doc_name),
        doc_missing=_doc_missing(doc_name),
        object_name=repr(object_name),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to list expressions",
        screenshot=False,
        document=doc_name,
        read_only=True,
    )


__all__ = [
    "clear_expression_operation",
    "list_expressions_operation",
    "set_expression_operation",
]
