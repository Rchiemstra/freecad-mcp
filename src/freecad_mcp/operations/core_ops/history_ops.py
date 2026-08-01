from __future__ import annotations

import logging

from ...freecad_client import FreeCADConnection
from ...responses import ToolResponse
from ...template_resources import render_template_text
from .run_code import _run_code

logger = logging.getLogger("FreeCADMCPserver")

def undo_operation(freecad: FreeCADConnection, doc_name: str) -> ToolResponse:
    code = render_template_text(
        "core/doc_action.py.txt",
        doc_name=repr(doc_name),
        action_line="_d.undo()",
        message=repr("undo done"),
    )
    return _run_code(freecad, True, code,
                     f"Undo performed on '{doc_name}'", "Failed to undo",
                     document=doc_name)

def redo_operation(freecad: FreeCADConnection, doc_name: str) -> ToolResponse:
    code = render_template_text(
        "core/doc_action.py.txt",
        doc_name=repr(doc_name),
        action_line="_d.redo()",
        message=repr("redo done"),
    )
    return _run_code(freecad, True, code,
                     f"Redo performed on '{doc_name}'", "Failed to redo",
                     document=doc_name)
