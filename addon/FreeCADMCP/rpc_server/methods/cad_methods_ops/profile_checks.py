"""Sketch profile validity checks shared by pad and pocket."""

from __future__ import annotations


def self_intersecting_wire_numbers(shape: object, part: object) -> list[int]:
    """1-based numbers of closed wires whose planar face OCCT reports invalid.

    A closed but self-intersecting wire (a bow-tie) passes ``isClosed`` and PartDesign
    silently reinterprets it; ``Part.Face(wire).isValid()`` is False for it.
    """
    make_face = getattr(part, "Face", None)
    if shape is None or not callable(make_face):
        return []
    numbers: list[int] = []
    for number, wire in enumerate(getattr(shape, "Wires", None) or [], start=1):
        try:
            if not wire.isClosed():
                continue
            valid = bool(make_face(wire).isValid())
        except Exception:
            # Only a definite OCCT verdict refuses the profile.
            continue
        if not valid:
            numbers.append(number)
    return numbers


__all__ = ["self_intersecting_wire_numbers"]
