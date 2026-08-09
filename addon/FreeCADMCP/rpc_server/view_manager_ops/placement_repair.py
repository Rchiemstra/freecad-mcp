"""Placement touch-and-refresh for leased model mutation."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import FreeCAD

from .refresh_view import refresh_active_view


def repair_placements_and_refresh(
    document_name: str,
    touch_objects: Sequence[str],
    *,
    fit: bool = False,
) -> dict[str, Any]:
    """Leased model mutation that reassigns Placement before refreshing."""
    try:
        doc = FreeCAD.getDocument(document_name)
        if doc is None:
            return {"ok": False, "error": f"Document {document_name!r} not found"}
        touched = []
        for name in touch_objects:
            obj = doc.getObject(name)
            if obj is None or not hasattr(obj, "Placement"):
                continue
            obj.Placement = obj.Placement
            touched.append(name)
        result = refresh_active_view(fit=fit)
        result["touched"] = touched
        return result
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
