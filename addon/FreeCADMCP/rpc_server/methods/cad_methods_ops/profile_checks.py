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


# mm^3; below this a PartDesign result is degenerate, not a thin part.
_MIN_SOLID_VOLUME = 1e-9


def solid_result_issue(shape: object) -> str | None:
    """Why a recomputed pad/pocket shape is not a usable solid, or None.

    ``isNull()`` alone lets through a pocket that removed everything (no solids,
    volume 0) and a pad of overlapping wires (one solid of volume -0.0).
    """
    if shape is None or bool(getattr(shape, "isNull", lambda: True)()):
        return "has no shape"
    if not list(getattr(shape, "Solids", None) or []):
        return "has no solid"
    volume = getattr(shape, "Volume", None)
    if isinstance(volume, bool) or not isinstance(volume, (int, float)) or not volume > _MIN_SOLID_VOLUME:
        return f"has no positive volume ({volume})"
    return None


__all__ = ["self_intersecting_wire_numbers", "solid_result_issue"]
