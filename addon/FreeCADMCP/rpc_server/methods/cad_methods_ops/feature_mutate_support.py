"""Mutation helpers for typed PartDesign / Part feature leaves."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from typing import cast

from .feature_lookup_support import MutableFeatureLike


def nonempty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value


def optional_name(value: object, field: str) -> str | None:
    if value is None:
        return None
    return nonempty_string(value, field)


def number_value(
    value: object,
    field: str,
    *,
    positive: bool = False,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{field} must be a number")
    number = float(value)
    if positive and number <= 0:
        raise ValueError(f"{field} must be > 0")
    if maximum is not None and number > maximum:
        raise ValueError(f"{field} must be <= {maximum:g}")
    return number


# A 500-occurrence PartDesign pattern boolean-cuts hundreds of tool shapes on
# the GUI thread (PartDesign::Transformed::execute) and can wedge FreeCAD for
# tens of minutes. 100 stays interactive.
MAX_PATTERN_OCCURRENCES = 100


def count_value(
    value: object,
    field: str,
    *,
    minimum: int,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    if value < minimum:
        raise ValueError(f"{field} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(
            f"{field} must be <= {maximum}; split the pattern or use fewer occurrences"
        )
    return value


def string_list(value: object, field: str, *, minimum: int = 0) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list of strings")
    names: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field} must contain nonempty strings")
        names.append(item)
    if len(names) < minimum:
        raise ValueError(f"{field} must contain at least {minimum} entries")
    return names


def bool_value(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def create_feature(
    document: object,
    body: object | None,
    object_type: str,
    name: str,
) -> MutableFeatureLike:
    if body is not None:
        factory = getattr(body, "newObject", None)
        if callable(factory):
            return cast(MutableFeatureLike, factory(object_type, name))
    factory = getattr(document, "addObject", None)
    if not callable(factory):
        raise RuntimeError("document cannot create objects")
    return cast(MutableFeatureLike, factory(object_type, name))


def set_attr(obj: object, name: str, value: object) -> None:
    setattr(obj, name, value)


def set_named_property(feature: object, names: Sequence[str], value: object) -> str:
    properties = set(getattr(feature, "PropertiesList", []))
    for name in names:
        if name in properties:
            set_attr(feature, name, value)
            return name
    if not properties:
        set_attr(feature, names[0], value)
        return names[0]
    raise RuntimeError("Feature does not support any of: " + ", ".join(names))


def set_feature_bool(feature: object, names: Sequence[str], value: bool) -> str | None:
    properties = set(getattr(feature, "PropertiesList", []))
    for name in names:
        if name in properties:
            set_attr(feature, name, bool(value))
            return name
    if not properties:
        set_attr(feature, names[0], bool(value))
        return names[0]
    if value:
        raise RuntimeError("Feature does not support any of: " + ", ".join(names))
    return None


def set_revolution_symmetric(feature: object, value: bool) -> str | None:
    """Set a symmetric revolution on builds with ``SideType`` or the legacy boolean."""
    properties = set(getattr(feature, "PropertiesList", []))
    if "SideType" in properties:
        set_attr(feature, "SideType", "Symmetric" if value else "One side")
        return "SideType"
    return set_feature_bool(feature, ("Symmetric", "Midplane"), value)


def set_originals(feature: object, source: object) -> str:
    properties = set(getattr(feature, "PropertiesList", []))
    if not properties or "Originals" in properties:
        set_attr(feature, "Originals", [source])
        return "Originals"
    if "Original" in properties:
        set_attr(feature, "Original", source)
        return "Original"
    raise RuntimeError("Pattern feature has no Originals/Original property")


def set_tip(body: object, feature: object) -> None:
    set_attr(body, "Tip", feature)


def require_nonempty_shape(feature: object, *, missing: str) -> None:
    shape = getattr(feature, "Shape", None)
    if shape is None or bool(getattr(shape, "isNull", lambda: True)()):
        raise LookupError(missing)


_SUBELEMENT_REF = re.compile(r"(Edge|Face|Vertex)(\d+)")
_SUBELEMENT_LISTS = {"Edge": "Edges", "Face": "Faces", "Vertex": "Vertexes"}


def require_subelements(source: object, refs: Sequence[str], field: str) -> None:
    """Reject ``EdgeN``/``FaceN``/``VertexN`` refs that *source* does not have.

    Other spellings (mapped topological names) are left to FreeCAD.
    """

    shape = getattr(source, "Shape", None)
    name = getattr(source, "Name", "?")
    for ref in refs:
        match = _SUBELEMENT_REF.fullmatch(ref)
        if match is None:
            continue
        elements = getattr(shape, _SUBELEMENT_LISTS[match.group(1)], None)
        if elements is None:
            continue
        index = int(match.group(2))
        if not 1 <= index <= len(elements):
            raise ValueError(
                f"{field}: {ref!r} does not exist on {name!r} "
                f"({len(elements)} {_SUBELEMENT_LISTS[match.group(1)].lower()})"
            )


def _abs_dot(left: object, right: object) -> float | None:
    try:
        return abs(float(left.dot(right)))  # type: ignore[attr-defined]
    except Exception:
        try:
            return abs(
                float(left.x) * float(right.x)
                + float(left.y) * float(right.y)
                + float(left.z) * float(right.z)
            )
        except Exception:
            return None


def _normal_on_edge(face: object, edge: object) -> object | None:
    curve = getattr(edge, "Curve", None)
    value = getattr(curve, "value", None)
    parameter = getattr(edge, "ParameterRange", None)
    surface = getattr(face, "Surface", None)
    parameter_of = getattr(surface, "parameter", None)
    normal_at = getattr(face, "normalAt", None)
    if not callable(value) or parameter is None or not callable(parameter_of) or not callable(normal_at):
        return None
    try:
        start, end = parameter[0], parameter[1]
        point = value((float(start) + float(end)) / 2.0)
        u_value, v_value = parameter_of(point)
        return normal_at(u_value, v_value)
    except Exception:
        return None


def _edge_not_c0(shape: object, edge_name: str) -> str | None:
    """Return why a dress-up would skip *edge_name*, or None when it is sharp."""

    match = _SUBELEMENT_REF.fullmatch(edge_name)
    if match is None or match.group(1) != "Edge" or shape is None:
        return None
    edges = getattr(shape, "Edges", None)
    if not edges:
        return None
    index = int(match.group(2)) - 1
    if not 0 <= index < len(edges):
        return None
    edge = edges[index]
    reported = getattr(edge, "face_continuity", None)
    if isinstance(reported, str) and reported != "C0":
        return f"{edge_name} is not C0 continuous"
    faces: list[object] = []
    finder = getattr(shape, "ancestorsOfType", None)
    if callable(finder):
        try:
            import Part

            faces = list(finder(edge, Part.Face) or [])
        except Exception:
            faces = []
    if len(faces) < 2:
        attached = getattr(edge, "Faces", None)
        if attached:
            faces = list(attached)
    if len(faces) < 2:
        return None
    first = _normal_on_edge(faces[0], edge)
    second = _normal_on_edge(faces[1], edge)
    if first is None or second is None:
        return None
    dot = _abs_dot(first, second)
    if dot is not None and dot > 0.999:
        return f"{edge_name} is not C0 continuous"
    return None


def require_c0_edges(source: object, refs: Sequence[str]) -> None:
    """Reject edges FreeCAD's chamfer and fillet would skip as not C0.

    Those edges otherwise disappear and the recompute says "No edges specified".
    """

    shape = getattr(source, "Shape", None)
    problems = [problem for ref in refs if (problem := _edge_not_c0(shape, ref))]
    if problems:
        raise ValueError("Cannot dress this edge: " + "; ".join(problems))


def require_within_extent(source: object, value: float, field: str) -> None:
    """Reject a dress-up size no smaller than the whole *source* shape.

    OpenCASCADE reports such sizes only as "BRep_API: command not done".
    """

    box = getattr(getattr(source, "Shape", None), "BoundBox", None)
    diagonal = getattr(box, "DiagonalLength", None)
    if not isinstance(diagonal, int | float) or not math.isfinite(diagonal):
        return
    if 0 < diagonal <= value:
        raise ValueError(
            f"{field} {value:g} does not fit on {getattr(source, 'Name', '?')!r} "
            f"(bounding-box diagonal {diagonal:.6g} mm)"
        )


def is_read_only_property(item: object, name: str) -> bool:
    checker = getattr(item, "isReadOnly", None)
    if callable(checker):
        try:
            return bool(checker(name))
        except Exception:
            pass
    editor_mode = getattr(item, "getEditorMode", None)
    if callable(editor_mode):
        try:
            mode = editor_mode(name)
            if isinstance(mode, (list, tuple)) and "ReadOnly" in mode:
                return True
        except Exception:
            pass
    return False


__all__ = [
    "bool_value",
    "count_value",
    "create_feature",
    "is_read_only_property",
    "nonempty_string",
    "number_value",
    "optional_name",
    "require_c0_edges",
    "require_nonempty_shape",
    "require_subelements",
    "require_within_extent",
    "set_attr",
    "set_feature_bool",
    "set_named_property",
    "set_originals",
    "set_tip",
    "string_list",
]
