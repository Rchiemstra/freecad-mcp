"""Document recompute with GUI idle barrier."""

from __future__ import annotations

from typing import Any

import FreeCAD

from ..gui_dispatch import _flush_gui_events


def recompute_and_wait(doc_name: str) -> dict[str, Any]:
    """Recompute a document and block until the GUI is idle again.

    Runs ``doc.recompute()`` on the GUI thread, drains the queued Qt events so
    the tree/3D view reflect the result, then reports per-object recompute state.
    An explicit recompute-complete + GUI-idle barrier: after this returns a
    follow-up model check sees a settled document, complementing the
    ``check_rpc_sync`` nonce probe (which only proves the queue is live).
    """
    doc = FreeCAD.getDocument(doc_name)
    if doc is None:
        return {"ok": False, "error": f"Document not found: {doc_name}"}

    touched = doc.recompute()
    _flush_gui_events()

    objects: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    pending: list[str] = []
    for obj in doc.Objects:
        st = list(getattr(obj, "State", []))
        try:
            valid = bool(obj.isValid())
        except Exception:
            valid = True
        entry = {"name": obj.Name, "state": st, "valid": valid}
        objects.append(entry)
        if (not valid) or any(s in ("Invalid", "Error", "Erroneous") for s in st):
            errors.append(entry)
        if "Touched" in st:
            pending.append(obj.Name)

    return {
        "ok": not errors,
        "document": doc.Name,
        "recomputed_count": int(touched) if isinstance(touched, int) else None,
        "objects": objects,
        "errors": errors,
        "pending_recompute": pending,
        "settled": not pending,
        "idle": True,
    }
