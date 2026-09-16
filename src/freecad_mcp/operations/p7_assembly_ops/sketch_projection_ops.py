from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ..parametric_ops.get_sketch_geometry import get_sketch_geometry_operation as _typed_get_sketch_geometry
from ..parametric_ops.sketch_add_external_projection import (
    sketch_add_external_projection_operation,
)


def get_sketch_geometry_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    sketch_name: str,
    include_constraints: bool = True,
    include_external: bool = True,
    global_coords: bool = True,
) -> ToolResponse:
    return _typed_get_sketch_geometry(
        freecad,
        doc_name,
        sketch_name,
        include_constraints,
        include_external,
        global_coords,
    )


__all__ = [
    "get_sketch_geometry_operation",
    "sketch_add_external_projection_operation",
]
