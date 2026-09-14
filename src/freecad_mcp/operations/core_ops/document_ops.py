from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...responses.tool_results import json_response
from ..parametric_ops.close_document import close_document_operation
from ..parametric_ops.create_document import create_document_operation
from ..parametric_ops.recompute_document import recompute_document_operation
from ..parametric_ops.reload_document import reload_document_operation

def list_documents_operation(freecad: FreeCADConnection) -> ToolResponse:
    return json_response(freecad.list_documents())


__all__ = [
    "close_document_operation",
    "create_document_operation",
    "list_documents_operation",
    "recompute_document_operation",
    "reload_document_operation",
]
