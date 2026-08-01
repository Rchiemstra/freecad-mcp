from __future__ import annotations

import logging
from typing import Any

from ...freecad_client import FreeCADConnection
from ...responses import ToolResponse, tool_fail
from .helpers import (
    _typed_rpc_unavailable,
    _typed_rpc_unavailable_result,
    _typed_sketch_attach_result,
)

logger = logging.getLogger("FreeCADMCPserver")


def _offset_breaks_typed_rpc(
    freecad: FreeCADConnection,
    attachment_offset: dict[str, Any] | None,
) -> bool:
    if attachment_offset is None:
        return False
    capability_probe = getattr(freecad, "supports_rpc_parameter", None)
    if not callable(capability_probe):
        return False
    try:
        offset_supported = capability_probe("sketch_attach", "attachment_offset")
    except Exception as exc:
        logger.warning("Could not inspect sketch_attach capabilities: %s", exc)
        return False
    if offset_supported is False:
        logger.info(
            "Addon predates sketch_attach attachment_offset; using "
            "generated fallback before mutation"
        )
        return True
    return False


def _try_typed_sketch_attach(
    typed,
    freecad: FreeCADConnection,
    *,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    support: str | dict[str, Any],
    attachment_offset: dict[str, Any] | None,
) -> ToolResponse | None:
    try:
        if attachment_offset is None:
            res = typed(doc_name, sketch_name, support)
        else:
            res = typed(doc_name, sketch_name, support, attachment_offset)
    except Exception as exc:
        if not _typed_rpc_unavailable(exc):
            logger.error("Typed sketch_attach failed: %s", exc)
            return tool_fail(f"Failed to attach sketch: {exc}")
        logger.info(
            "Typed sketch_attach unavailable (%s); using generated fallback",
            exc,
        )
        return None
    if _typed_rpc_unavailable_result(res):
        logger.info(
            "Typed sketch_attach is absent in the authenticated addon; "
            "using generated fallback"
        )
        return None
    return _typed_sketch_attach_result(res, only_text_feedback=only_text_feedback)
