"""Sketcher constraint distance/angle helpers (Phase 4 slice 4F)."""

from __future__ import annotations


def _apply_distance_constraint(
    sketch, constraint: dict, *, sketcher
) -> tuple[int | None, str | None]:
    if "geo2" in constraint:
        idx = sketch.addConstraint(
            sketcher.Constraint(
                "Distance",
                constraint["geo1"],
                constraint.get("pos1", 0),
                constraint["geo2"],
                constraint.get("pos2", 0),
                constraint["value"],
            )
        )
        return idx, None
    if "pos" in constraint:
        idx = sketch.addConstraint(
            sketcher.Constraint(
                "Distance", constraint["geo"], constraint["pos"], constraint["value"]
            )
        )
        return idx, None
    idx = sketch.addConstraint(
        sketcher.Constraint("Distance", constraint["geo"], constraint["value"])
    )
    return idx, None


def _apply_distance_axis_constraint(
    sketch, constraint: dict, axis: str, *, sketcher
) -> tuple[int | None, str | None]:
    if "pos" in constraint:
        idx = sketch.addConstraint(
            sketcher.Constraint(
                axis, constraint["geo"], constraint["pos"], constraint["value"]
            )
        )
        return idx, None
    idx = sketch.addConstraint(
        sketcher.Constraint(axis, constraint["geo"], constraint["value"])
    )
    return idx, None


def _apply_angle_constraint(
    sketch, constraint: dict, *, sketcher
) -> tuple[int | None, str | None]:
    if "geo2" in constraint:
        idx = sketch.addConstraint(
            sketcher.Constraint(
                "Angle",
                constraint["geo1"],
                constraint.get("pos1", 0),
                constraint["geo2"],
                constraint.get("pos2", 0),
                constraint["value"],
            )
        )
        return idx, None
    idx = sketch.addConstraint(
        sketcher.Constraint("Angle", constraint["geo"], constraint["value"])
    )
    return idx, None
