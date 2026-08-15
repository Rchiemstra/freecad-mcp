from __future__ import annotations

import logging
from typing import Any

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...responses.tool_results import tool_fail
from ...template_resources import render_template_lines
from ..p7_assembly import _run_json_code
from .helpers import (
    _doc_missing,
    _generated_sketch_attach,
    _typed_parametric_mutation,
)
from .sketch_attach_helpers import _offset_breaks_typed_rpc, _try_typed_sketch_attach

logger = logging.getLogger("FreeCADMCPserver")

def sketch_attach_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    support: str | dict[str, Any],
    attachment_offset: dict[str, Any] | None = None,
) -> ToolResponse:
    """Attach a sketch via typed RPC; generated code only if RPC is missing."""
    typed = getattr(freecad, "sketch_attach", None)
    if _offset_breaks_typed_rpc(freecad, attachment_offset):
        typed = None
    if callable(typed):
        typed_result = _try_typed_sketch_attach(
            typed,
            freecad,
            only_text_feedback=only_text_feedback,
            doc_name=doc_name,
            sketch_name=sketch_name,
            support=support,
            attachment_offset=attachment_offset,
        )
        if typed_result is not None:
            return typed_result

    return _generated_sketch_attach(
        freecad,
        only_text_feedback,
        doc_name,
        sketch_name,
        support,
        attachment_offset,
    )

def sketch_edit_constraint_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    value: float | None = None,
    name: str | None = None,
    index: int | None = None,
) -> ToolResponse:
    if name is None and index is None:
        return tool_fail("Provide constraint name=... or index=... (prefer name after trim/fillet)")
    return _typed_parametric_mutation(
        freecad,
        only_text_feedback,
        "sketch_edit_constraint",
        (doc_name, sketch_name, value, name, index),
        "Failed to edit constraint",
    )

def diagnose_parametric_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    object_name: str | None = None,
) -> ToolResponse:
    lines = render_template_lines(
        "parametric/diagnose_parametric.py.txt",
        doc_name=repr(doc_name),
        doc_missing=_doc_missing(doc_name),
        object_name=repr(object_name),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to diagnose parametric model",
        screenshot=False,
        document=doc_name,
        read_only=True,
    )
