"""Sketcher constraint delete helpers (Phase 4 slice 4F)."""

from __future__ import annotations


def sketch_delete_error(code, message, **details):
    return {
        "success": False,
        "error_code": code,
        "error": message,
        **details,
    }


def resolve_constraint_delete_indices(sketch, indices, names):
    constraints = list(getattr(sketch, "Constraints", []) or [])
    invalid_indices = sorted({index for index in indices if index >= len(constraints)})
    if invalid_indices:
        return None, sketch_delete_error(
            "CONSTRAINT_INDEX_OUT_OF_RANGE",
            "Constraint index out of range: "
            + ", ".join(str(index) for index in invalid_indices),
            invalid_indices=invalid_indices,
            constraint_count=len(constraints),
        )
    resolved = set(indices)
    for name in names:
        matches = [
            index
            for index, constraint in enumerate(constraints)
            if getattr(constraint, "Name", "") == name
        ]
        if not matches:
            return None, sketch_delete_error(
                "CONSTRAINT_NOT_FOUND",
                f"Constraint name not found: {name}",
                constraint_name=name,
            )
        if len(matches) > 1:
            return None, sketch_delete_error(
                "CONSTRAINT_NAME_AMBIGUOUS",
                f"Constraint name is not unique: {name}",
                constraint_name=name,
                matching_indices=matches,
            )
        resolved.add(matches[0])
    return sorted(resolved), None
