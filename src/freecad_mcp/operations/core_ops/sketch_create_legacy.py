from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...template_resources import render_template_lines, render_template_text
from .run_code import _run_code


def sketch_create_legacy_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    body_name: str | None = None,
    attach_to: str | None = None,
) -> ToolResponse:
    attachment_code = ""
    if attach_to:
        if attach_to in ("XY_Plane", "XZ_Plane", "YZ_Plane"):
            attachment_code = render_template_text(
                "core/attach_origin_plane.py.txt",
                attach_to=repr(attach_to),
            ).strip()
        elif ":" in attach_to:
            obj_n, face = attach_to.split(":", 1)
            attachment_code = render_template_text(
                "core/attach_face.py.txt",
                obj_name=repr(obj_n),
                face_name=repr(face),
            ).strip()
    lines = render_template_lines(
        "core/sketch_create.py.txt",
        doc_name=repr(doc_name),
        doc_missing=repr(f"Document {doc_name!r} not found"),
        body_name=repr(body_name),
        body_missing=repr(f"Body {body_name!r} not found"),
        sketch_name=repr(sketch_name),
        attachment_code=attachment_code,
    )
    return _run_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        f"Sketch '{sketch_name}' created",
        "Failed to create sketch",
        document=doc_name,
    )
