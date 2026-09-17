# mypy: ignore-errors
"""Read-only diagnostics helpers for typed query handlers."""

from __future__ import annotations

import os
import tempfile
import time
import uuid
from contextlib import suppress

from .typed_runtime import TypedMutationError, require_object
from .typed_rpc_container_support import snapshot_rings


def _vec(value: object) -> dict[str, float] | None:
    if value is None:
        return None
    return {
        "x": round(float(getattr(value, "x", 0.0)), 6),
        "y": round(float(getattr(value, "y", 0.0)), 6),
        "z": round(float(getattr(value, "z", 0.0)), 6),
    }


def capture_state(document: object, object_names: list[str] | None) -> dict[str, object]:
    targets = object_names or [str(getattr(obj, "Name", "")) for obj in getattr(document, "Objects", []) or []]
    captured: dict[str, dict[str, object]] = {}
    for name in targets:
        obj = require_object(document, name)
        placement = getattr(obj, "Placement", None)
        row: dict[str, object] = {
            "name": str(getattr(obj, "Name", name)),
            "type": str(getattr(obj, "TypeId", "")),
            "placement_base": _vec(getattr(placement, "Base", None)) if placement is not None else None,
            "bbox": None,
            "face_count": None,
        }
        shape = getattr(obj, "Shape", None)
        if shape is not None and not getattr(shape, "isNull", lambda: True)():
            try:
                box = shape.BoundBox
                row["bbox"] = {
                    "xmin": round(float(box.XMin), 6),
                    "ymin": round(float(box.YMin), 6),
                    "zmin": round(float(box.ZMin), 6),
                    "xmax": round(float(box.XMax), 6),
                    "ymax": round(float(box.YMax), 6),
                    "zmax": round(float(box.ZMax), 6),
                }
            except Exception:
                row["bbox"] = None
            try:
                row["face_count"] = len(shape.Faces)
            except Exception:
                row["face_count"] = None
        captured[str(getattr(obj, "Name", name))] = row
    return {"doc": str(getattr(document, "Name", "")), "objects": captured}


def list_expressions(document: object, object_name: str) -> dict[str, object]:
    obj = require_object(document, object_name)
    expressions: list[dict[str, object]] = []
    engine = getattr(obj, "ExpressionEngine", None)
    if engine:
        for item in engine:
            try:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    expressions.append({"prop": str(item[0]), "expression": str(item[1])})
                else:
                    expressions.append({"raw": str(item)})
            except Exception as exc:
                expressions.append({"error": str(exc)})
    return {"object": str(getattr(obj, "Name", object_name)), "expressions": expressions, "count": len(expressions)}


def get_recompute_log(document: object) -> dict[str, object]:
    log = getattr(document, "RecomputeLog", None)
    if log is None:
        return {"entries": [], "count": 0}
    entries = [str(item) for item in log]
    return {"entries": entries, "count": len(entries)}


def get_sketch_diagnostics(document: object, sketch_name: str) -> dict[str, object]:
    sketch = require_object(document, sketch_name)
    return {
        "sketch_name": str(getattr(sketch, "Name", sketch_name)),
        "geometry_count": int(getattr(sketch, "GeometryCount", 0)),
        "constraint_count": int(getattr(sketch, "ConstraintCount", 0)),
        "conflict": bool(getattr(sketch, "ConstraintCount", 0) and getattr(sketch, "solveFailed", lambda: False)()),
    }




def diagnose_parametric(document: object, object_name: str | None) -> dict[str, object]:
    targets = [require_object(document, object_name)] if object_name else list(getattr(document, "Objects", []) or [])
    targets = [t for t in targets if t is not None]
    if object_name and not targets:
        raise TypedMutationError(f"Object not found: {object_name}")
    invalid: list[dict[str, object]] = []
    expression_issues: list[dict[str, object]] = []
    sketches: list[dict[str, object]] = []
    for obj in targets:
        state = list(getattr(obj, "State", []))
        if any(s in ("Invalid", "Error") for s in state):
            invalid.append({
                "name": str(getattr(obj, "Name", "")),
                "label": str(getattr(obj, "Label", getattr(obj, "Name", ""))),
                "type": str(getattr(obj, "TypeId", "")),
                "state": state,
            })
        engine = getattr(obj, "ExpressionEngine", None) or []
        for item in engine:
            try:
                prop = str(item[0]) if isinstance(item, (list, tuple)) and item else "?"
                expr = str(item[1]) if isinstance(item, (list, tuple)) and len(item) >= 2 else str(item)
                bound = obj.getExpression(prop) if hasattr(obj, "getExpression") else None
                if bound is None and expr:
                    expression_issues.append({"object": str(getattr(obj, "Name", "")), "prop": prop, "expression": expr, "issue": "missing_binding"})
            except Exception as exc:
                expression_issues.append({"object": str(getattr(obj, "Name", "")), "issue": "expression_error", "message": str(exc)})
        if getattr(obj, "TypeId", "") == "Sketcher::SketchObject":
            sketches.append({
                "name": str(getattr(obj, "Name", "")),
                "geometry_count": len(getattr(obj, "Geometry", []) or []),
                "constraint_count": len(getattr(obj, "Constraints", []) or []),
                "state": state,
                "conflicting": list(getattr(obj, "ConflictingConstraints", []) or []),
                "redundant": list(getattr(obj, "RedundantConstraints", []) or []),
                "malformed": list(getattr(obj, "MalformedConstraints", []) or []),
            })
    return {"invalid": invalid, "invalid_objects": invalid, "expression_issues": expression_issues, "sketches": sketches, "object_filter": object_name}


def get_recompute_log_full(document: object) -> dict[str, object]:
    results: list[dict[str, object]] = []
    for obj in getattr(document, "Objects", []) or []:
        try:
            state = list(getattr(obj, "State", []))
            exprs: list[dict[str, object]] = []
            for item in getattr(obj, "ExpressionEngine", None) or []:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    exprs.append({"prop": str(item[0]), "expression": str(item[1])})
                else:
                    exprs.append({"raw": str(item)})
            entry: dict[str, object] = {
                "name": str(getattr(obj, "Name", "")),
                "label": str(getattr(obj, "Label", getattr(obj, "Name", ""))),
                "type": str(getattr(obj, "TypeId", "")),
                "state": state,
                "valid": not any(s in ("Invalid", "Error") for s in state),
                "expression_count": len(exprs),
            }
            if exprs:
                entry["expressions"] = exprs
            results.append(entry)
        except Exception as exc:
            results.append({"name": str(getattr(obj, "Name", "?")), "error": str(exc)})
    return {"total": len(getattr(document, "Objects", []) or []), "objects": results}


_SNAPSHOT_STORE: dict[str, dict[str, object]] = {}


def snapshot_document(document: object) -> dict[str, object]:
    payload = capture_state(document, None)
    rings = snapshot_rings(document)
    fd, path = tempfile.mkstemp(suffix=".FCStd", prefix="mcp_snap_")
    os.close(fd)
    try:
        save_copy_with_outcome = getattr(document, "saveCopyWithOutcome", None)
        if callable(save_copy_with_outcome):
            save_outcome = save_copy_with_outcome(path)
            if not isinstance(save_outcome, dict) or not save_outcome.get("success"):
                raise RuntimeError(
                    str(
                        save_outcome.get("message")
                        or save_outcome.get("error_code")
                        or "FreeCAD rejected the snapshot copy"
                    )
                    if isinstance(save_outcome, dict)
                    else "FreeCAD returned an invalid snapshot outcome"
                )
        else:
            save_copy = getattr(document, "saveCopy", None)
            if not callable(save_copy):
                raise RuntimeError("document cannot save a snapshot copy")
            save_copy(path)
    except Exception:
        with suppress(Exception):
            os.remove(path)
        raise
    known_ids = {
        row.get("id")
        for ring in rings
        for row in ring
        if isinstance(row, dict)
    }
    snapshot_id = "snap-" + str(int(time.time() * 1000))
    if snapshot_id in known_ids:
        snapshot_id = str(uuid.uuid4())
    row = {
        "id": snapshot_id,
        "path": path,
        "doc": str(getattr(document, "Name", "") or payload.get("doc", "")),
        "t": time.time(),
    }
    for ring in rings:
        ring.append(row)
        while len(ring) > 5:
            old = ring.pop(0)
            if not isinstance(old, dict):
                continue
            old_path = old.get("path")
            if not isinstance(old_path, str) or not old_path:
                continue
            still_referenced = any(
                isinstance(item, dict) and item.get("path") == old_path
                for other in rings
                for item in other
            )
            if not still_referenced:
                with suppress(Exception):
                    os.remove(old_path)
    _SNAPSHOT_STORE[snapshot_id] = payload
    return {
        "snapshot_id": snapshot_id,
        "doc": str(payload.get("doc", "")),
        "count": max(len(ring) for ring in rings),
    }


def run_transaction(document: object, label: str, code: str, dry_run: bool, commit_on_success: bool) -> dict[str, object]:
    document.openTransaction(label)
    committed = False
    try:
        namespace: dict[str, object] = {"doc": document}
        exec(code, namespace, namespace)
        document.recompute()
        if dry_run:
            document.abortTransaction()
        elif commit_on_success:
            document.commitTransaction()
            committed = True
        else:
            document.abortTransaction()
    except Exception:
        document.abortTransaction()
        try:
            document.recompute()
        except Exception:
            pass
        raise
    return {"ok": True, "label": label, "committed": committed, "dry_run": bool(dry_run)}


__all__ = [
    "capture_state",
    "get_recompute_log",
    "get_sketch_diagnostics",
    "list_expressions",
    "diagnose_parametric",
    "get_recompute_log_full",
    "snapshot_document",
    "run_transaction",
]

