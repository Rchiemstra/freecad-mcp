from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from .diagnose_parametric import diagnose_parametric_operation as _typed_diagnose_parametric
from .sketch_attach import sketch_attach_operation
from .sketch_edit_constraint import sketch_edit_constraint_operation


def diagnose_parametric_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    object_name: str | None = None,
) -> ToolResponse:
    return _typed_diagnose_parametric(freecad, only_text_feedback, doc_name, object_name)


__all__ = [
    "diagnose_parametric_operation",
    "sketch_attach_operation",
    "sketch_edit_constraint_operation",
]
