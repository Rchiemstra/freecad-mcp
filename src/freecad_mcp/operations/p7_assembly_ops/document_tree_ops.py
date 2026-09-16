from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ..parametric_ops.create_datum_plane import create_datum_plane_operation
from ..parametric_ops.create_part_container import create_part_container_operation
from ..parametric_ops.create_subshape_binder import create_subshape_binder_operation
from ..parametric_ops.get_document_tree import get_document_tree_operation as _typed_get_document_tree
from ..parametric_ops.move_object import move_object_operation


def get_document_tree_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    root_filter: str | None = None,
    max_depth: int = 4,
    include: list[str] | None = None,
    include_properties: list[str] | None = None,
    selected_nodes: list[str] | None = None,
) -> ToolResponse:
    return _typed_get_document_tree(
        freecad,
        doc_name,
        root_filter or "",
        max_depth,
        include,
        include_properties,
        selected_nodes,
    )


__all__ = [
    "create_datum_plane_operation",
    "create_part_container_operation",
    "create_subshape_binder_operation",
    "get_document_tree_operation",
    "move_object_operation",
]
