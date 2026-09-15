"""Mutation helpers for typed PartDesign / Part feature leaves."""

from __future__ import annotations

from collections.abc import Sequence


def nonempty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value


def optional_name(value: object, field: str) -> str | None:
    if value is None:
        return None
    return nonempty_string(value, field)


def number_value(value: object, field: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{field} must be a number")
    number = float(value)
    if positive and number <= 0:
        raise ValueError(f"{field} must be > 0")
    return number


def count_value(value: object, field: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    if value < minimum:
        raise ValueError(f"{field} must be >= {minimum}")
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
) -> object:
    if body is not None:
        factory = getattr(body, "newObject", None)
        if callable(factory):
            return factory(object_type, name)
    factory = getattr(document, "addObject", None)
    if not callable(factory):
        raise RuntimeError("document cannot create objects")
    return factory(object_type, name)


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
    "require_nonempty_shape",
    "set_attr",
    "set_feature_bool",
    "set_named_property",
    "set_originals",
    "set_tip",
    "string_list",
]
