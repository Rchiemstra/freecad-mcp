from __future__ import annotations

import logging

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ..parametric_ops.audit_hardcoded_dimensions import (
    audit_hardcoded_dimensions_operation as _typed_audit_hardcoded_dimensions,
)
from ..parametric_ops.get_dependency_graph import (
    get_dependency_graph_operation as _typed_get_dependency_graph,
)
from ..parametric_ops.inspect_geometry import (
    inspect_geometry_operation as _typed_inspect_geometry,
)
from ..parametric_ops.match_subshape import match_subshape_operation as _typed_match_subshape

logger = logging.getLogger("FreeCADMCPserver")


def audit_hardcoded_dimensions_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    body_name: str,
    flag_aliases: bool = True,
) -> ToolResponse:
    del only_text_feedback
    return _typed_audit_hardcoded_dimensions(freecad, doc_name, body_name, flag_aliases)


def inspect_geometry_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    object_name: str,
    subshape: str | None = None,
    activate: bool = False,
    restore_active_document: bool = True,
) -> ToolResponse:
    del only_text_feedback, restore_active_document
    if activate:
        try:
            freecad.activate_document(doc_name)
        except Exception as exc:
            logger.warning("inspect_geometry activate_document failed: %s", exc)
        try:
            selection = [f"{object_name}:{subshape}"] if subshape else [object_name]
            freecad.select_subshapes(doc_name, selection, clear=True)
        except Exception as exc:
            logger.warning("inspect_geometry select_subshapes failed: %s", exc)
    return _typed_inspect_geometry(freecad, doc_name, object_name, subshape)


def get_dependency_graph_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    root: str,
) -> ToolResponse:
    del only_text_feedback
    return _typed_get_dependency_graph(freecad, doc_name, root)


def match_subshape_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    source_object: str,
    source_subshape: str,
    target_object: str,
    limit: int = 10,
    tolerance: float = 1.0,
) -> ToolResponse:
    del only_text_feedback
    return _typed_match_subshape(
        freecad, doc_name, source_object, source_subshape, target_object, limit, tolerance
    )
