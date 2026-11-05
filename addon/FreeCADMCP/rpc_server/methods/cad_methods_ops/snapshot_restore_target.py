"""Snapshot restore target resolution (Phase 4 slice 4F)."""

from __future__ import annotations

import os
from typing import cast

import FreeCAD

from .snapshot_owner import row_belongs_to_document

_MISMATCH: dict[str, object] = {
    "ok": False,
    "error_code": "SNAPSHOT_DOCUMENT_MISMATCH",
    "error": "Snapshot belongs to a different document",
}


def _record(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    return cast(dict[str, object], value)


def resolve_restore_target(
    document: object,
    snapshot_id: str | None,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    snaps = getattr(FreeCAD, "_mcp_snapshots", [])
    if not isinstance(snaps, list):
        snaps = []
    if snapshot_id:
        for snap in snaps:
            record = _record(snap)
            if record is not None and record.get("id") == snapshot_id:
                return record, None
        return None, {"ok": False, "error": f"Snapshot not found: {snapshot_id}"}
    for snap in reversed(snaps):
        record = _record(snap)
        if record is not None and row_belongs_to_document(record, document):
            return record, None
    if snaps:
        return None, dict(_MISMATCH)
    return None, {"ok": False, "error": "No snapshots available to restore"}


def validate_restore_target(
    target: dict[str, object],
    document: object,
) -> dict[str, object] | None:
    if not row_belongs_to_document(target, document):
        return dict(_MISMATCH)
    path = target.get("path")
    if not isinstance(path, str) or not os.path.exists(path):
        return {"ok": False, "error": f"Snapshot file missing: {path}"}
    return None
