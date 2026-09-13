from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...template_resources import render_template_lines
from .helpers import _doc_preamble, _run_json_code, _shared_helpers
from freecad_mcp.operations.parametric_ops.create_datum_plane import create_datum_plane_operation
from freecad_mcp.operations.parametric_ops.create_part_container import create_part_container_operation
from freecad_mcp.operations.parametric_ops.create_subshape_binder import create_subshape_binder_operation
from freecad_mcp.operations.parametric_ops.move_object import move_object_operation


def get_document_tree_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    root_filter: str | None = None,
    max_depth: int = 4,
    include: list[str] | None = None,
    include_properties: list[str] | None = None,
    selected_nodes: list[str] | None = None,
) -> ToolResponse:
    lines = _doc_preamble(doc_name) + _shared_helpers() + render_template_lines(
        "p7_assembly/get_document_tree.py.txt",
        root_filter=repr(root_filter),
        max_depth=repr(max_depth),
        include=repr(include),
        include_properties=repr(include_properties),
        selected_nodes=repr(selected_nodes),
    )
    return _run_json_code(
        freecad,
        True,
        "\n".join(lines),
        "Failed to get document tree",
        document=doc_name,
        read_only=True,
    )


__all__ = [
    "create_datum_plane_operation",
    "create_part_container_operation",
    "create_subshape_binder_operation",
    "get_document_tree_operation",
    "move_object_operation",
]
