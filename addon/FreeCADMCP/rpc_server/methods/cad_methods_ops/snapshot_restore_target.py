"""Snapshot restore target resolution (Phase 4 slice 4F)."""

from __future__ import annotations

import os

import FreeCAD

from ...snapshot_service import recovery_snapshot_path


def resolve_restore_target(
    doc_name: str,
    snapshot_id: str | None,
    *,
    active,
    lease_snapshot_id: str | None,
) -> tuple[dict | None, dict | None]:
    snaps = getattr(FreeCAD, "_mcp_snapshots", [])
    if active is not None and (snapshot_id is None or snapshot_id == lease_snapshot_id):
        if not lease_snapshot_id:
            return None, {
                "ok": False,
                "error_code": "LEASE_BASELINE_SNAPSHOT_MISSING",
                "error": "The active lease has no recovery baseline snapshot",
            }
        return (
            {
                "id": lease_snapshot_id,
                "path": str(recovery_snapshot_path(lease_snapshot_id)),
                "doc": doc_name,
            },
            None,
        )
    if snapshot_id:
        for snap in snaps:
            if snap["id"] == snapshot_id:
                return snap, None
        return None, {"ok": False, "error": f"Snapshot not found: {snapshot_id}"}
    if not snaps:
        return None, {"ok": False, "error": "No snapshots available to restore"}
    return snaps[-1], None


def validate_restore_target(target: dict, doc_name: str) -> dict | None:
    if str(target.get("doc") or "") != doc_name:
        return {
            "ok": False,
            "error_code": "SNAPSHOT_DOCUMENT_MISMATCH",
            "error": "Snapshot belongs to a different document",
        }
    if not os.path.exists(target["path"]):
        return {"ok": False, "error": f"Snapshot file missing: {target['path']}"}
    return None
