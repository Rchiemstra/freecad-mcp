from __future__ import annotations

import logging

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...template_resources import render_template_text
from ..p7_assembly import _doc_preamble, _run_json_code
from .helpers import _diag_preamble

logger = logging.getLogger("FreeCADMCPserver")

def audit_hardcoded_dimensions_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    body_name: str,
    flag_aliases: bool = True,
) -> ToolResponse:
    code = [*_doc_preamble(doc_name), render_template_text(
        "diagnostics/audit_hardcoded_dimensions.py.txt",
        body_name=repr(body_name),
        flag_aliases=repr(flag_aliases),
    )]
    return _run_json_code(
        freecad, only_text_feedback, "\n".join(code),
        "Failed hard-coded dimension audit",
        screenshot=False,
        document=doc_name,
        read_only=True,
    )

def inspect_geometry_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    object_name: str,
    subshape: str | None = None,
    activate: bool = False,
    restore_active_document: bool = True,
) -> ToolResponse:
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

    code = [*_diag_preamble(doc_name), render_template_text(
        "diagnostics/inspect_geometry.py.txt",
        object_name=repr(object_name),
        subshape=repr(subshape),
    )]
    return _run_json_code(
        freecad, only_text_feedback, "\n".join(code),
        "Failed geometry inspection",
        screenshot=False,
        document=doc_name,
        read_only=True,
    )

def get_dependency_graph_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    root: str,
) -> ToolResponse:
    code = [*_doc_preamble(doc_name), render_template_text(
        "diagnostics/get_dependency_graph.py.txt",
        root=repr(root),
    )]
    return _run_json_code(
        freecad, only_text_feedback, "\n".join(code),
        "Failed to build dependency graph",
        screenshot=False,
        document=doc_name,
        read_only=True,
    )

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
    code = [*_diag_preamble(doc_name), render_template_text(
        "diagnostics/match_subshape.py.txt",
        source_object=repr(source_object),
        source_subshape=repr(source_subshape),
        target_object=repr(target_object),
        limit=repr(limit),
        tolerance=repr(tolerance),
    )]
    return _run_json_code(
        freecad, only_text_feedback, "\n".join(code),
        "Failed subshape matching",
        screenshot=False,
        document=doc_name,
        read_only=True,
    )
