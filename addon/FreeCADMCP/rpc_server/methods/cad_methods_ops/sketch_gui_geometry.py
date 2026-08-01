"""CAD RPC helpers extracted from ``FreeCADRPC`` (Phase 4 slice 4F)."""

from __future__ import annotations

import contextlib

from ._common import _rpc_mod
from .sketch_geometry_ops import add_sketch_geometry_item
from .sketch_gui_constraints import sketch_delete_error


def sketch_add_geometry_gui(doc_name, sketch_name, geometry):
    try:
        doc = _rpc_mod().FreeCAD.getDocument(doc_name)
        if not doc:
            return f"Document '{doc_name}' not found."
        sketch = doc.getObject(sketch_name)
        if not sketch:
            return f"Sketch '{sketch_name}' not found."

        indices = []
        for geom in geometry:
            added, error = add_sketch_geometry_item(sketch, geom)
            if error:
                return error
            indices.extend(added)

        doc.recompute()
        return indices
    except Exception as e:
        return str(e)


def sketch_delete_geometry_gui(
    doc_name,
    sketch_name,
    geometry_indices,
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
        if not hasattr(sketch, "delGeometries"):
            return sketch_delete_error(
                "NOT_A_SKETCH",
                f"Object '{sketch_name}' is not an editable Sketcher sketch.",
            )

        indices = list(geometry_indices or [])
        if not indices:
            return sketch_delete_error(
                "INVALID_ARGUMENT",
                "geometry_indices must be a non-empty list.",
            )
        if any(
            isinstance(index, bool)
            or not isinstance(index, int)
            or index < 0
            for index in indices
        ):
            return sketch_delete_error(
                "INVALID_ARGUMENT",
                "geometry_indices must contain non-negative integers.",
            )

        geometry = list(getattr(sketch, "Geometry", []) or [])
        invalid_indices = sorted(
            {index for index in indices if index >= len(geometry)}
        )
        if invalid_indices:
            return sketch_delete_error(
                "GEOMETRY_INDEX_OUT_OF_RANGE",
                (
                    "Geometry index out of range: "
                    + ", ".join(str(index) for index in invalid_indices)
                ),
                invalid_indices=invalid_indices,
                geometry_count=len(geometry),
            )

        target_indices = sorted(set(indices))
        deleted = []
        for index in target_indices:
            construction = None
            with contextlib.suppress(Exception):
                construction = bool(sketch.getConstruction(index))
            deleted.append(
                {
                    "index": index,
                    "type": str(
                        getattr(geometry[index], "TypeId", "")
                        or type(geometry[index]).__name__
                    ),
                    "construction": construction,
                }
            )

        constraint_count_before = len(
            list(getattr(sketch, "Constraints", []) or [])
        )
        sketch.delGeometries(target_indices)
        doc.recompute()
        remaining_geometry_count = len(
            list(getattr(sketch, "Geometry", []) or [])
        )
        remaining_constraint_count = len(
            list(getattr(sketch, "Constraints", []) or [])
        )
        return {
            "success": True,
            "sketch": str(getattr(sketch, "Name", sketch_name)),
            "deleted_geometry": deleted,
            "deleted_count": len(target_indices),
            "remaining_geometry_count": remaining_geometry_count,
            "dependent_constraints_removed": max(
                0,
                constraint_count_before - remaining_constraint_count,
            ),
            "remaining_constraint_count": remaining_constraint_count,
        }
    except Exception as exc:
        return sketch_delete_error(
            "SKETCH_GEOMETRY_DELETE_FAILED",
            str(exc),
        )
