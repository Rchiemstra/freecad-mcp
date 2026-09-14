from __future__ import annotations

from collections.abc import Mapping

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from .helpers import _generated_sketch_attach


def sketch_attach_legacy_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    support: str | Mapping[str, object],
    attachment_offset: Mapping[str, object] | None = None,
) -> ToolResponse:
    return _generated_sketch_attach(
        freecad,
        only_text_feedback,
        doc_name,
        sketch_name,
        support,
        attachment_offset,
    )
