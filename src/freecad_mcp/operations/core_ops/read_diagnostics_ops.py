from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ..parametric_ops.get_recompute_log import (
    get_recompute_log_operation as _typed_get_recompute_log,
)
from ..parametric_ops.get_sketch_diagnostics import (
    get_sketch_diagnostics_operation as _typed_get_sketch_diagnostics,
)


def get_recompute_log_operation(freecad: FreeCADConnection, doc_name: str) -> ToolResponse:
    return _typed_get_recompute_log(freecad, doc_name)


def get_sketch_diagnostics_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    sketch_name: str,
) -> ToolResponse:
    return _typed_get_sketch_diagnostics(freecad, doc_name, sketch_name)
