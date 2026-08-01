"""Sketcher constraint dispatch table (Phase 4 slice 4F)."""

from __future__ import annotations

from collections.abc import Callable

import Sketcher

from .sketch_constraint_apply import (
    _apply_angle_constraint,
    _apply_distance_axis_constraint,
    _apply_distance_constraint,
)


def _coincident(sketch, constraint: dict):
    return (
        sketch.addConstraint(
            Sketcher.Constraint(
                "Coincident",
                constraint["geo1"],
                constraint["pos1"],
                constraint["geo2"],
                constraint["pos2"],
            )
        ),
        None,
    )


def _horizontal(sketch, constraint: dict):
    return sketch.addConstraint(Sketcher.Constraint("Horizontal", constraint["geo"])), None


def _vertical(sketch, constraint: dict):
    return sketch.addConstraint(Sketcher.Constraint("Vertical", constraint["geo"])), None


def _radius(sketch, constraint: dict):
    return (
        sketch.addConstraint(
            Sketcher.Constraint("Radius", constraint["geo"], constraint["value"])
        ),
        None,
    )


def _diameter(sketch, constraint: dict):
    return (
        sketch.addConstraint(
            Sketcher.Constraint("Diameter", constraint["geo"], constraint["value"])
        ),
        None,
    )


def _parallel(sketch, constraint: dict):
    return (
        sketch.addConstraint(
            Sketcher.Constraint("Parallel", constraint["geo1"], constraint["geo2"])
        ),
        None,
    )


def _perpendicular(sketch, constraint: dict):
    return (
        sketch.addConstraint(
            Sketcher.Constraint("Perpendicular", constraint["geo1"], constraint["geo2"])
        ),
        None,
    )


def _equal(sketch, constraint: dict):
    return (
        sketch.addConstraint(
            Sketcher.Constraint("Equal", constraint["geo1"], constraint["geo2"])
        ),
        None,
    )


def _symmetric(sketch, constraint: dict):
    return (
        sketch.addConstraint(
            Sketcher.Constraint(
                "Symmetric",
                constraint["geo1"],
                constraint["pos1"],
                constraint["geo2"],
                constraint["pos2"],
                constraint["geo3"],
                constraint.get("pos3", 0),
            )
        ),
        None,
    )


def _point_on_object(sketch, constraint: dict):
    return (
        sketch.addConstraint(
            Sketcher.Constraint(
                "PointOnObject",
                constraint["geo1"],
                constraint["pos1"],
                constraint["geo2"],
            )
        ),
        None,
    )


def _tangent(sketch, constraint: dict):
    return (
        sketch.addConstraint(
            Sketcher.Constraint("Tangent", constraint["geo1"], constraint["geo2"])
        ),
        None,
    )


def _block(sketch, constraint: dict):
    return sketch.addConstraint(Sketcher.Constraint("Block", constraint["geo"])), None


_CONSTRAINT_HANDLERS: dict[str, Callable] = {
    "Coincident": _coincident,
    "Horizontal": _horizontal,
    "Vertical": _vertical,
    "Distance": _apply_distance_constraint,
    "DistanceX": lambda sketch, c: _apply_distance_axis_constraint(sketch, c, "DistanceX"),
    "DistanceY": lambda sketch, c: _apply_distance_axis_constraint(sketch, c, "DistanceY"),
    "Radius": _radius,
    "Diameter": _diameter,
    "Angle": _apply_angle_constraint,
    "Parallel": _parallel,
    "Perpendicular": _perpendicular,
    "Equal": _equal,
    "Symmetric": _symmetric,
    "PointOnObject": _point_on_object,
    "Tangent": _tangent,
    "Block": _block,
}


def apply_sketch_constraint(sketch, constraint: dict) -> tuple[int | None, str | None]:
    handler = _CONSTRAINT_HANDLERS.get(constraint.get("type", ""))
    if handler is None:
        return None, f"Unknown constraint type: '{constraint.get('type', '')}'"
    return handler(sketch, constraint)
