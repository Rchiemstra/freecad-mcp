"""Sketcher constraint delete/edit GUI handlers (Phase 4 slice 4F)."""

from __future__ import annotations

from ._common import _rpc_mod
from .sketch_constraint_delete_helpers import (
    resolve_constraint_delete_indices,
    sketch_delete_error,
)
from .sketch_gui_constraints_add import sketch_add_constraint_gui

__all__ = [
    "sketch_add_constraint_gui",
    "sketch_delete_constraint_gui",
    "sketch_edit_constraint_gui",
]


def sketch_delete_constraint_gui(
    doc_name,
    sketch_name,
    constraint_indices,
    constraint_names,
):
    try:
        doc = _rpc_mod().FreeCAD.getDocument(doc_name)
        if not doc:
            return sketch_delete_error(
                "DOCUMENT_NOT_FOUND",
                f"Document '{doc_name}' not found.",
            )
        sketch = doc.getObject(sketch_name)
        if not sketch:
            return sketch_delete_error(
                "SKETCH_NOT_FOUND",
                f"Sketch '{sketch_name}' not found.",
            )
        if not hasattr(sketch, "delConstraints"):
            return sketch_delete_error(
                "NOT_A_SKETCH",
                f"Object '{sketch_name}' is not an editable Sketcher sketch.",
            )

        indices = list(constraint_indices or [])
        names = list(constraint_names or [])
        if not indices and not names:
            return sketch_delete_error(
                "INVALID_ARGUMENT",
                "Provide at least one constraint index or name.",
            )
        if any(
            isinstance(index, bool) or not isinstance(index, int) or index < 0
            for index in indices
        ):
            return sketch_delete_error(
                "INVALID_ARGUMENT",
                "constraint_indices must contain non-negative integers.",
            )
        if any(not isinstance(name, str) or not name for name in names):
            return sketch_delete_error(
                "INVALID_ARGUMENT",
                "constraint_names must contain non-empty strings.",
            )

        target_indices, error = resolve_constraint_delete_indices(sketch, indices, names)
        if error:
            return error

        constraints = list(getattr(sketch, "Constraints", []) or [])
        deleted = [
            {
                "index": index,
                "name": str(getattr(constraints[index], "Name", "") or ""),
                "type": str(getattr(constraints[index], "Type", "") or ""),
            }
            for index in target_indices
        ]
        sketch.delConstraints(target_indices, True)
        doc.recompute()
        return {
            "success": True,
            "sketch": str(getattr(sketch, "Name", sketch_name)),
            "deleted_constraints": deleted,
            "deleted_count": len(target_indices),
            "remaining_constraint_count": len(
                list(getattr(sketch, "Constraints", []) or [])
            ),
        }
    except Exception as exc:
        return sketch_delete_error(
            "SKETCH_CONSTRAINT_DELETE_FAILED",
            str(exc),
        )


def sketch_edit_constraint_gui(doc_name, sketch_name, value, name, index):
    try:
        doc = _rpc_mod().FreeCAD.getDocument(doc_name)
        if not doc:
            return f"Document '{doc_name}' not found."
        sketch = doc.getObject(sketch_name)
        if not sketch:
            return f"Sketch '{sketch_name}' not found."
        idx = _resolve_constraint_index(sketch, value, name, index)
        if isinstance(idx, str):
            return idx
        if value is not None:
            sketch.setDatum(idx, float(value))
        doc.recompute()
        after = None
        try:
            after = float(sketch.getDatum(idx))
        except Exception:
            after = None
        return {
            "success": True,
            "sketch": sketch.Name,
            "index": idx,
            "name": getattr(sketch.Constraints[idx], "Name", ""),
            "after": after,
        }
    except Exception as e:
        return str(e)


def _resolve_constraint_index(sketch, value, name, index):
    del value
    if name is not None:
        for i, constraint in enumerate(getattr(sketch, "Constraints", []) or []):
            if getattr(constraint, "Name", "") == name:
                return i
        return f"Constraint name not found: {name}"
    if index is not None:
        return int(index)
    return "Provide constraint name or index"
