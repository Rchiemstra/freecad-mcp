"""Validate shape and semantic subelement references in worker jobs."""

from __future__ import annotations

import re
from typing import Any

from ..worker_protocol_types.protocol_error import ProtocolError

_SUBELEMENT_RE = re.compile(r"^(Face|Edge|Vertex)([1-9][0-9]*)$")
_SKETCHER_PSEUDO_SUBELEMENTS = frozenset(
    {"H_Axis", "V_Axis", "N_Axis", "RootPoint"}
)


def _is_null_subobject(value: Any) -> bool:
    if value is None:
        return True
    is_null = getattr(value, "isNull", None)
    if callable(is_null):
        try:
            return bool(is_null())
        except Exception:
            return False
    return False


def _subelement_name_is_safe(name: str) -> bool:
    """Reject empty or path-like names; allow semantic identifiers such as H_Axis."""
    if not name or name in {".", ".."}:
        return False
    if any(ord(ch) < 32 for ch in name):
        return False
    if "/" in name or "\\" in name:
        return False
    return ".." not in name


def _is_sketcher_pseudo_subelement(target: Any, name: str) -> bool:
    """Return whether FreeCAD defines ``name`` semantically on this sketch."""

    if name not in _SKETCHER_PSEUDO_SUBELEMENTS:
        return False
    type_id = str(getattr(target, "TypeId", "") or "")
    if type_id.startswith("Sketcher::SketchObject"):
        return True
    is_derived_from = getattr(target, "isDerivedFrom", None)
    if not callable(is_derived_from):
        return False
    try:
        return bool(is_derived_from("Sketcher::SketchObject"))
    except Exception:
        return False


def _resolve_via_get_subobject(target: Any, name: str) -> Any | None:
    getter = getattr(target, "getSubObject", None)
    if not callable(getter):
        return None
    try:
        resolved = getter(name)
    except Exception:
        return None
    if _is_null_subobject(resolved):
        return None
    return resolved


def _resolve_via_shape_element(shape: Any, name: str) -> Any | None:
    getter = getattr(shape, "getElement", None)
    if not callable(getter):
        return None
    try:
        resolved = getter(name)
    except Exception:
        return None
    if _is_null_subobject(resolved):
        return None
    return resolved


def subelement_resolvable_by_freecad_fallback(target: Any, subelement: str) -> bool:
    """Return whether FreeCAD can still resolve a stale element-map subelement."""
    name = str(subelement)
    if _resolve_via_get_subobject(target, name) is not None:
        return True
    shape = getattr(target, "Shape", None)
    return shape is not None and _resolve_via_shape_element(shape, name) is not None


def validate_subelement_reference(target: Any, subelement: str) -> None:
    """Resolve a shape or semantic subelement and reject nonexistent references.

    Indexed ``FaceN``/``EdgeN``/``VertexN`` names are validated against shape
    collections. Known Sketcher pseudo-subelements are accepted on sketch
    targets; other safe names are resolved via ``target.getSubObject``, with
    ``Shape.getElement`` as a fallback.
    """
    name = str(subelement)
    owner = getattr(target, "Name", "<unknown>")
    shape = getattr(target, "Shape", None)
    match = _SUBELEMENT_RE.fullmatch(name)
    if match:
        if shape is None:
            raise ProtocolError(f"{owner}.{name} has no target shape")
        collection_name = {
            "Face": "Faces",
            "Edge": "Edges",
            "Vertex": "Vertexes",
        }[match.group(1)]
        collection = getattr(shape, collection_name, None)
        index = int(match.group(2))
        if collection is None or index > len(collection):
            raise ProtocolError(f"{owner}.{name} does not exist")
        return
    if not _subelement_name_is_safe(name):
        raise ProtocolError(f"{owner}.{name} does not exist")
    if _is_sketcher_pseudo_subelement(target, name):
        return
    if _resolve_via_get_subobject(target, name) is not None:
        return
    if shape is not None and _resolve_via_shape_element(shape, name) is not None:
        return
    if shape is None and not callable(getattr(target, "getSubObject", None)):
        raise ProtocolError(f"{owner}.{name} has no target shape")
    raise ProtocolError(f"{owner}.{name} does not exist")
