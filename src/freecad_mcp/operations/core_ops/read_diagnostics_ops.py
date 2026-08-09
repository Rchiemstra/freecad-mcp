from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...template_resources import render_template_text
from .run_code import _run_code


def get_recompute_log_operation(freecad: FreeCADConnection, doc_name: str) -> ToolResponse:
    code = render_template_text("core/get_recompute_log.py.txt", doc_name=repr(doc_name))
    return _run_code(freecad, True, code,
                     f"Recompute log for '{doc_name}'", "Failed to get recompute log",
                     document=doc_name, recompute="none", capture_view=False,
                     read_only=True, execution_mode="worker")

def get_sketch_diagnostics_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    sketch_name: str,
) -> ToolResponse:
    code = render_template_text(
        "core/get_sketch_diagnostics.py.txt",
        doc_name=repr(doc_name),
        sketch_name=repr(sketch_name),
    )
    return _run_code(freecad, True, code,
                     f"Sketch diagnostics for '{sketch_name}'", "Failed to get sketch diagnostics",
                     document=doc_name, recompute="none", capture_view=False,
                     read_only=True, execution_mode="worker")
