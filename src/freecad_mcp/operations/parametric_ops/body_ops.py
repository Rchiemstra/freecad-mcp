from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from .helpers import _typed_parametric_mutation


def body_create_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    body_name: str,
) -> ToolResponse:
    return _typed_parametric_mutation(
        freecad,
        only_text_feedback,
        "body_create",
        (doc_name, body_name),
        "Failed to create body",
    )

def body_set_tip_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    body_name: str,
    feature_name: str,
) -> ToolResponse:
    return _typed_parametric_mutation(
        freecad,
        only_text_feedback,
        "body_set_tip",
        (doc_name, body_name, feature_name),
        "Failed to set body tip",
    )
