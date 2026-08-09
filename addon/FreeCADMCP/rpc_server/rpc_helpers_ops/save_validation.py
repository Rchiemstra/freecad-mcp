import json
import os
import re

from ._common import RpcHelperDependencies

"""Saved-document worker validation helpers."""

_SAVE_VALIDATION_MARKER = "__FREECAD_MCP_SAVE_VALIDATION__"


def _saved_document_expectations(document):
    """Capture the live invariants that the reopened FCStd must preserve."""
    objects = sorted(
        str(getattr(item, "Name", ""))
        for item in getattr(document, "Objects", ())
        if getattr(item, "Name", None)
    )
    bodies = {}
    for item in getattr(document, "Objects", ()):
        if str(getattr(item, "TypeId", "")) != "PartDesign::Body":
            continue
        group = sorted(
            str(getattr(member, "Name", ""))
            for member in getattr(item, "Group", ())
            if getattr(member, "Name", None)
        )
        tip = getattr(getattr(item, "Tip", None), "Name", None)
        bodies[str(item.Name)] = {"members": group, "tip": tip}
    return {"objects": objects, "bodies": bodies}


def _validate_saved_document_worker(
    path,
    document_name,
    profile,
    expected,
    dependencies: RpcHelperDependencies,
):
    """Reopen and recompute the saved file in the matching FreeCADCmd worker."""
    manager = dependencies.worker_manager
    if manager is None:
        return {"ok": False, "error": "matching FreeCADCmd worker is unavailable"}
    workspace = manager.create_workspace()
    safe_name = re.sub(r"[^A-Za-z0-9_]", "_", str(document_name or "Document"))
    if not safe_name or safe_name[0].isdigit():
        safe_name = "Document_" + safe_name
    load_path = workspace / "load" / f"{safe_name}.FCStd"
    snapshot = {
        "ok": True,
        "primary_document": safe_name,
        "snapshot_duration_ms": 0.0,
        "active_document": safe_name,
        "selection": [],
        "documents": [
            {
                "document_name": safe_name,
                "document_label": safe_name,
                "document_uid": "",
                "document_id": "",
                "original_filename": str(path),
                "modified": False,
                "object_count": len(expected.get("objects", ())),
                "dependencies": [],
                "has_pending_transaction": False,
                "transacting": False,
                "last_modified_date": "",
                "snapshot_filename": os.path.basename(path),
                "snapshot_path": str(path),
                "load_filename": load_path.name,
                "load_path": str(load_path),
                "primary": True,
            }
        ],
        "expected_links": [],
        "ignored_links": [],
        "link_policy": "strict",
        "state_indicators_best_effort": True,
    }
    code = f"""\
import json
doc = FreeCAD.ActiveDocument
errors = []
objects = sorted(obj.Name for obj in doc.Objects)
bodies = {{}}
for obj in doc.Objects:
    shape = getattr(obj, "Shape", None)
    if shape is not None and hasattr(shape, "isNull") and not shape.isNull():
        if hasattr(shape, "isValid") and not shape.isValid():
            errors.append("invalid_shape:" + obj.Name)
    if getattr(obj, "TypeId", "") == "PartDesign::Body":
        members = sorted(item.Name for item in getattr(obj, "Group", []))
        tip = getattr(getattr(obj, "Tip", None), "Name", None)
        if tip is not None and tip not in members:
            errors.append("body_tip_not_member:" + obj.Name + ":" + tip)
        bodies[obj.Name] = {{"members": members, "tip": tip}}
_marker = {_SAVE_VALIDATION_MARKER!r}
_payload = json.dumps({{"objects": objects, "bodies": bodies, "errors": errors}}, sort_keys=True)
print(_marker + _payload)
"""
    result = manager.execute(
        code,
        {"timeout_seconds": 120, "recompute": "target"},
        snapshot,
        workspace,
    )
    if not result.get("success"):
        return {
            "ok": False,
            "profile": profile,
            "error": result.get("error") or result.get("message") or "worker failed",
            "error_code": result.get("error_code"),
        }
    output = str(result.get("message") or "")
    marker_at = output.find(_SAVE_VALIDATION_MARKER)
    if marker_at < 0:
        return {"ok": False, "error": "worker validation result was missing"}
    encoded = output[marker_at + len(_SAVE_VALIDATION_MARKER) :].splitlines()[0]
    try:
        actual = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        return {"ok": False, "error": f"invalid worker validation result: {exc}"}
    differences = {}
    if actual.get("objects") != expected.get("objects"):
        differences["objects"] = {
            "expected": expected.get("objects"),
            "actual": actual.get("objects"),
        }
    if actual.get("bodies") != expected.get("bodies"):
        differences["bodies"] = {
            "expected": expected.get("bodies"),
            "actual": actual.get("bodies"),
        }
    if actual.get("errors"):
        differences["errors"] = actual["errors"]
    return {
        "ok": not differences,
        "worker_reopened": True,
        "recomputed": True,
        "profile": profile,
        "differences": differences,
    }
