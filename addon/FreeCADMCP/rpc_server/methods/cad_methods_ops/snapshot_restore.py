"""CAD RPC helpers extracted from ``FreeCADRPC`` (Phase 4 slice 4F)."""

import contextlib
import os
import tempfile
import time

import FreeCAD

from ...mutation_guard import validate_document_invariants
from ...snapshot_service_ops.restore_snapshot import restore_snapshot_in_place_gui
from .snapshot_restore_target import resolve_restore_target, validate_restore_target


def snapshot(self, doc_name: str) -> dict:
    """I7 — save the current document into a ring buffer of the last 5
    snapshots kept on the FreeCAD module (shared with the execute_code
    snapshot tool). Returns {ok, snapshot_id, doc, count}."""
    res = self._dispatch_gui(lambda: snapshot_gui(doc_name))
    if isinstance(res, dict):
        return res
    return {"ok": False, "error": res}


def restore(self, doc_name: str, snapshot_id: str | None = None) -> dict:
    """I7 — restore a snapshot in place (closes the current doc and reopens
    the snapshot file). Latest snapshot when snapshot_id is None. Shares the
    FreeCAD._mcp_snapshots ring buffer with the execute_code restore tool."""
    res = self._dispatch_gui(lambda: restore_gui(self, doc_name, snapshot_id))
    if isinstance(res, dict):
        return res
    return {"ok": False, "error": res}


def snapshot_gui(doc_name: str):

    try:
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            return {"ok": False, "error": f"Document '{doc_name}' not found."}
        if not hasattr(FreeCAD, "_mcp_snapshots"):
            FreeCAD._mcp_snapshots = []
        fd, path = tempfile.mkstemp(suffix=".FCStd", prefix="mcp_snap_")
        os.close(fd)
        try:
            doc.saveCopy(path)
        except Exception as e:
            with contextlib.suppress(Exception):
                os.remove(path)
            return {"ok": False, "error": f"Failed to save snapshot: {e}"}
        sid = "snap-" + str(int(time.time() * 1000))
        FreeCAD._mcp_snapshots.append(
            {"id": sid, "path": path, "doc": doc.Name, "t": time.time()}
        )
        while len(FreeCAD._mcp_snapshots) > 5:
            old = FreeCAD._mcp_snapshots.pop(0)
            with contextlib.suppress(Exception):
                os.remove(old["path"])
        return {
            "ok": True,
            "snapshot_id": sid,
            "doc": doc.Name,
            "count": len(FreeCAD._mcp_snapshots),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def restore_gui(self, doc_name: str, snapshot_id):
    try:
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            return {"ok": False, "error": f"Document '{doc_name}' not found."}
        target, error = resolve_restore_target(doc_name, snapshot_id)
        if error:
            return error
        validation_error = validate_restore_target(target, doc_name)
        if validation_error:
            return validation_error
        snaps = getattr(FreeCAD, "_mcp_snapshots", [])
        return _restore_unleased_snapshot(doc, target, snaps)
    except Exception as e:
        return {
            "ok": False,
            "error_code": getattr(e, "code", "SNAPSHOT_RESTORE_FAILED"),
            "error": str(e),
        }
def _restore_unleased_snapshot(doc, target, snaps):
    cur = doc.Name
    result = restore_snapshot_in_place_gui(
        doc,
        target["path"],
        expected_document_name=cur,
        expected_source_path=str(getattr(doc, "FileName", "") or "") or None,
        validator=validate_document_invariants,
    )
    return {
        **result,
        "restored_id": target["id"],
        "doc": cur,
        "new_doc": cur,
        "count": len(snaps),
    }
