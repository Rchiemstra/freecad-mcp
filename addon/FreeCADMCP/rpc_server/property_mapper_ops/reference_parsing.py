"""Reference list parsing for property assignment."""

from __future__ import annotations

from typing import Any

import FreeCAD


def to_shape_color(val: Any) -> tuple[float, float, float, float]:
    """Normalise a color to a 4-float RGBA tuple."""
    if not isinstance(val, (list, tuple)) or len(val) not in (3, 4):
        raise ValueError(
            f"ShapeColor must be an RGB or RGBA sequence, got {val!r}."
        )
    r, g, b = (float(val[0]), float(val[1]), float(val[2]))
    a = float(val[3]) if len(val) == 4 else 1.0
    return (r, g, b, a)


def parse_reference_entry(entry: Any) -> tuple[str, Any]:
    """Normalise a single ``References`` entry to ``(object_name, sub_element)``."""
    if isinstance(entry, dict):
        ref_name = entry.get("object_name", entry.get("Object"))
        face = entry.get("face", entry.get("Face"))
        if ref_name is None:
            raise ValueError(
                f"Reference entry {entry!r} is missing an 'object_name' key."
            )
        return ref_name, face
    if isinstance(entry, (list, tuple)) and len(entry) == 2:
        return entry[0], entry[1]
    raise ValueError(
        f"Invalid reference entry {entry!r}; expected "
        "{'object_name': ..., 'face': ...} or [object_name, face]."
    )


def resolve_references(doc: FreeCAD.Document, val: Any) -> list[tuple[Any, Any]]:
    """Resolve a ``References`` list into ``(DocumentObject, sub_element)`` tuples."""
    refs = []
    for entry in val:
        ref_name, face = parse_reference_entry(entry)
        ref_obj = doc.getObject(ref_name)
        if ref_obj is None:
            raise ValueError(f"Referenced object '{ref_name}' not found.")
        refs.append((ref_obj, face))
    return refs
