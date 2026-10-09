"""Selection parsing helpers for subshape selection."""

from __future__ import annotations

from typing import Any


def parse_selection_entry(item: Any) -> tuple[str, str, str | None]:
    """Return (object_name, sub_name, error_message)."""
    if isinstance(item, str):
        if ":" in item:
            obj_name, sub = item.split(":", 1)
            return obj_name.strip(), sub.strip(), None
        return item.strip(), "", None
    if isinstance(item, dict):
        obj_name = str(
            item.get("object")
            or item.get("obj")
            or item.get("name")
            or ""
        ).strip()
        sub = str(
            item.get("sub")
            or item.get("subshape")
            or item.get("subName")
            or ""
        ).strip()
        return obj_name, sub, None
    return "", "", f"Unsupported selection entry: {item!r}"


def subshape_missing(obj: Any, sub: str) -> bool:
    """True when ``sub`` is not an element of ``obj``.

    ``getSubObject`` without a real element name returns the owner, so a missing
    face such as ``Face99`` looks present. ``Shape.getElement`` is the check
    that returns None for a name the shape does not contain.
    """

    if not sub:
        return False
    shape = getattr(obj, "Shape", None)
    getter = getattr(shape, "getElement", None) if shape is not None else None
    if callable(getter):
        try:
            element = getter(sub)
        except Exception:
            return True
        if element is None or element is obj:
            return True
        is_null = getattr(element, "isNull", None)
        if callable(is_null):
            try:
                if is_null():
                    return True
            except Exception:
                return True
        return False
    get_subobject = getattr(obj, "getSubObject", None)
    if callable(get_subobject):
        try:
            return get_subobject(sub) is None
        except Exception:
            return True
    return False
