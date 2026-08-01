"""Sketcher constraint add GUI handler (Phase 4 slice 4F)."""

from __future__ import annotations

import contextlib

import FreeCAD

from .sketch_constraint_dispatch import apply_sketch_constraint


def sketch_add_constraint_gui(doc_name, sketch_name, constraints):
    try:
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            return f"Document '{doc_name}' not found."
        sketch = doc.getObject(sketch_name)
        if not sketch:
            return f"Sketch '{sketch_name}' not found."

        for constraint in constraints:
            idx, error = apply_sketch_constraint(sketch, constraint)
            if error:
                return error
            name = constraint.get("name")
            if name and idx is not None:
                with contextlib.suppress(Exception):
                    sketch.renameConstraint(idx, str(name))

        doc.recompute()
        return True
    except Exception as e:
        return str(e)
