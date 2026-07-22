"""Typed snapshot/restore operations for the addon-owned snapshot lifecycle."""
from __future__ import annotations

import logging

from ..freecad_client import FreeCADConnection
from ..responses import ToolResponse, json_response, text_response

logger = logging.getLogger("FreeCADMCPserver")


def snapshot_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
) -> ToolResponse:
    """I7 — snapshot the current document into a ring buffer of the last 5 states.

    Returns JSON ``{ok, snapshot_id, doc, count}``. Use before a risky mutating
    step so it can be undone with ``restore``.
    """
    try:
        result = freecad.invoke_rpc("snapshot", doc_name)
        if isinstance(result, dict):
            return json_response(result)
        return text_response(f"Failed to snapshot document: {result}")
    except Exception as exc:
        logger.error("Failed to snapshot document: %s", exc)
        return text_response(f"Failed to snapshot document: {exc}")


def restore_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    snapshot_id: str | None = None,
) -> ToolResponse:
    """I7 — restore a snapshot, replacing the current document in place.

    If ``snapshot_id`` is omitted, the most recent snapshot is restored. Returns
    JSON ``{ok, restored_id, doc, new_doc, count}``.
    """
    try:
        result = None
        if isinstance(freecad, FreeCADConnection):
            result = freecad._invoke_mutation_v2(
                "restore",
                {"doc_name": doc_name, "snapshot_id": snapshot_id},
                document_names=(doc_name,),
                operation_name="Restore document snapshot",
            )
        if result is None:
            result = freecad.invoke_rpc("restore", doc_name, snapshot_id)
        if isinstance(result, dict):
            return json_response(result)
        return text_response(f"Failed to restore snapshot: {result}")
    except Exception as exc:
        logger.error("Failed to restore snapshot: %s", exc)
        return text_response(f"Failed to restore snapshot: {exc}")
