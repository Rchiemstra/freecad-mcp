"""GUI-thread recompute-and-wait barrier."""

from __future__ import annotations

from typing import Any

import FreeCAD

from ..gui_dispatch import _flush_gui_events

#: Extra forced passes attempted when a plain recompute leaves objects touched.
#: A forced pass re-executes every object instead of only the dirty ones, so it
#: is bounded: two passes clear the ordinary "an execute() touched something
#: upstream of itself" case, and anything still touched after that is reported
#: rather than retried indefinitely.
MAX_FORCED_PASSES = 2


def _touched_names(doc) -> set[str]:
    names: set[str] = set()
    for obj in doc.Objects:
        try:
            if "Touched" in list(getattr(obj, "State", [])):
                names.add(obj.Name)
        except Exception:
            pass
    return names


def _dependency_cycle_members(doc) -> list[str]:
    """Names of objects that reach themselves through their own dependencies.

    A cycle cannot be resolved by recomputing harder: every pass re-touches the
    next member, so forcing would spin.  Report it instead.
    """
    members: list[str] = []
    for obj in doc.Objects:
        try:
            if any(dep.Name == obj.Name for dep in obj.OutListRecursive):
                members.append(obj.Name)
        except Exception:
            pass
    return sorted(members)


def _invoked_count(result: Any) -> int | None:
    return int(result) if isinstance(result, int) else None


def recompute_and_wait(doc_name: str) -> dict[str, Any]:
    """Recompute a document and block until the GUI is idle again.

    Runs ``doc.recompute()`` on the GUI thread, drains the queued Qt events so
    the tree/3D view reflect the result, then reports per-object recompute state.

    The recompute outcome is reported as three separate facts rather than one
    count, because they answer different questions and routinely disagree:

    ``invoked``
        how many features the recompute actually ran.
    ``stabilized``
        which objects were dirty beforehand and are clean now -- the work that
        actually landed.
    ``pending_recompute``
        which objects are still dirty afterwards.  A non-empty list next to a
        large ``invoked`` means the recompute ran and did not settle, which is
        a different failure from "the recompute never ran".
    """
    doc = FreeCAD.getDocument(doc_name)
    if doc is None:
        return {"ok": False, "error": f"Document not found: {doc_name}"}

    touched_before = _touched_names(doc)
    invoked = _invoked_count(doc.recompute())

    cycle = _dependency_cycle_members(doc)
    remaining = _touched_names(doc)
    forced_passes: list[dict[str, Any]] = []
    # A cycle is reported, not retried: forcing cannot converge on one.
    while remaining and not cycle and len(forced_passes) < MAX_FORCED_PASSES:
        previous = remaining
        try:
            forced_invoked = _invoked_count(doc.recompute(None, True))
        except Exception as exc:  # a forced pass must not mask the first result
            forced_passes.append({"invoked": None, "error": str(exc)})
            break
        remaining = _touched_names(doc)
        forced_passes.append(
            {"invoked": forced_invoked, "still_touched": sorted(remaining)}
        )
        if not remaining or len(remaining) >= len(previous):
            # No progress: another identical pass would not make any either.
            break

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

    still_touched = set(pending)
    return {
        "ok": not errors,
        "document": doc.Name,
        "recomputed_count": invoked,
        "invoked": invoked,
        "stabilized": sorted(touched_before - still_touched),
        "newly_touched": sorted(still_touched - touched_before),
        "touched_before": sorted(touched_before),
        "forced_passes": forced_passes,
        "dependency_cycle": cycle,
        "objects": objects,
        "errors": errors,
        "pending_recompute": pending,
        "settled": not pending,
        "idle": True,
    }


__all__ = ["MAX_FORCED_PASSES", "recompute_and_wait"]
