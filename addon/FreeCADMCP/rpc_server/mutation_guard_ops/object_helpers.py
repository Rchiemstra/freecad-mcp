"""FreeCAD document-object introspection helpers."""

from __future__ import annotations

from typing import Any


def object_name(value: Any) -> str:
    return str(getattr(value, "Name", "") or "")


def object_state(value: Any) -> tuple[str, ...]:
    try:
        return tuple(sorted(str(item) for item in (getattr(value, "State", ()) or ())))
    except Exception:
        return ()


def object_status_string(value: Any) -> str | None:
    """Return ``getStatusString()`` when bound; otherwise ``None``."""

    method = getattr(value, "getStatusString", None)
    if not callable(method):
        return None
    try:
        text = method()
    except Exception:
        return None
    if text is None:
        return None
    text = str(text).strip()
    return text or None


def object_is_valid(value: Any) -> bool | None:
    method = getattr(value, "isValid", None)
    if not callable(method):
        return None
    try:
        return bool(method())
    except Exception:
        return None


def shape_hash(value: Any) -> str:
    shape = getattr(value, "Shape", None)
    if shape is None:
        return ""
    for name in ("hashCode", "HashCode"):
        method = getattr(shape, name, None)
        if callable(method):
            try:
                return str(method())
            except Exception:
                break
    try:
        return str(hash(shape))
    except Exception:
        return ""


def shape_is_null(value: Any) -> bool | None:
    shape = getattr(value, "Shape", None)
    if shape is None:
        return None
    method = getattr(shape, "isNull", None)
    if not callable(method):
        return None
    try:
        return bool(method())
    except Exception:
        return None


def shape_is_valid(value: Any) -> bool | None:
    shape = getattr(value, "Shape", None)
    if shape is None:
        return None
    method = getattr(shape, "isValid", None)
    if not callable(method):
        return None
    try:
        return bool(method())
    except Exception:
        return None


def body_tip_issue(value: Any) -> str | None:
    try:
        is_body = value.isDerivedFrom("PartDesign::Body")
    except Exception:
        is_body = getattr(value, "TypeId", "") == "PartDesign::Body"
    if not is_body:
        return None
    group = tuple(getattr(value, "Group", ()) or ())
    tip = getattr(value, "Tip", None)
    if tip is None or tip in group:
        return None
    return f"{object_name(value) or '<body>'}.Tip"


def object_signature(value: Any, *, include_shape_hash: bool) -> tuple[Any, ...]:
    placement = getattr(value, "Placement", None)
    return (
        str(getattr(value, "TypeId", "") or ""),
        str(getattr(value, "Label", "") or ""),
        object_state(value),
        bool(getattr(value, "Touched", False)),
        repr(placement)[:512] if placement is not None else "",
        shape_hash(value) if include_shape_hash else "",
    )
