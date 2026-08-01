from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses import ToolResponse
from ...template_resources import render_template_text
from ..p7_assembly import _doc_preamble, _run_json_code


def preview_attachment_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    datum_name: str,
) -> ToolResponse:
    """I1 — preview an existing datum's attachment.

    Returns the support reference, the support face/edge global centre and
    normal, the datum's global base/normal, the owning bodies and their
    placements, ``source_body_placement_dropped`` (the P1 risk flag), and a
    signed distance + normal-angle diff between the datum and its support.

    Read-only. Saves the agent from rebuilding the whole model to discover that
    a cross-body datum dropped the source body's placement.
    """
    code = [*_doc_preamble(doc_name), render_template_text(
        "diagnostics/preview_attachment.py.txt",
        datum_name=repr(datum_name),
    )]
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(code),
        "Failed to preview attachment",
        screenshot=False,
        document=doc_name,
        read_only=True,
    )
