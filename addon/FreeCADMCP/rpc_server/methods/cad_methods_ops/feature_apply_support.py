"""Shared apply helpers for typed PartDesign / Part feature mutations."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, cast


class FeatureLike(Protocol):
    """Narrow created-object surface shared by typed feature leaves."""

    @property
    def Name(self) -> str: ...

    @property
    def Label(self) -> str: ...

    @property
    def TypeId(self) -> str: ...

    def isDerivedFrom(self, type_name: str) -> bool: ...


class MutableFeatureLike(FeatureLike, Protocol):
    """Mutation surface returned by document/body factories."""

    Visibility: bool

    def newObject(self, object_type: str, name: str) -> MutableFeatureLike: ...

    @property
    def Group(self) -> Sequence[object]: ...

    @property
    def PropertiesList(self) -> Sequence[str]: ...


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


def is_derived_from(obj: object, type_name: str) -> bool:
    checker = getattr(obj, "isDerivedFrom", None)
    if callable(checker):
        try:
            return bool(checker(type_name))
        except (AttributeError, TypeError):
            pass
    return getattr(obj, "TypeId", None) == type_name


def lookup_object(document: object, name: str) -> object | None:
    getter = getattr(document, "getObject", None)
    if not callable(getter):
        return None
    found = getter(name)
    if found is None:
        return None
    return cast(object, found)


def require_object(document: object, name: str, *, missing: str) -> object:
    obj = lookup_object(document, name)
    if obj is None:
        raise LookupError(missing)
    return obj


def require_absent(document: object, name: str) -> None:
    if lookup_object(document, name) is not None:
        raise FileExistsError(name)


def find_owning_body(document: object, source: object) -> object | None:
    objects = getattr(document, "Objects", ())
    for obj in objects:
        if getattr(obj, "TypeId", "") == "PartDesign::Body" and source in getattr(
            obj, "Group", []
        ):
            return cast(object, obj)
    return None


def resolve_optional_body(
    document: object,
    source: object,
    body_name: str | None,
) -> object | None:
    if body_name:
        body = lookup_object(document, body_name)
        if body is None:
            raise LookupError(f"Body not found: {body_name!r}")
        return body
    return find_owning_body(document, source)


def require_body(document: object, source: object, body_name: str | None) -> object:
    body = resolve_optional_body(document, source, body_name)
    if body is None:
        raise LookupError("Source feature must be inside a PartDesign Body")
    return body


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


def set_originals(feature: object, source: object) -> str:
    properties = set(getattr(feature, "PropertiesList", []))
    if not properties or "Originals" in properties:
        set_attr(feature, "Originals", [source])
        return "Originals"
    if "Original" in properties:
        set_attr(feature, "Original", source)
        return "Original"
    raise RuntimeError("Pattern feature has no Originals/Original property")


def _origin_name_variants(name: str) -> set[str]:
    return {name, name.replace("_", "-"), name.replace("-", "_")}


def _origin_feature(container: object, name: str) -> object | None:
    origin = getattr(container, "Origin", None)
    variants = _origin_name_variants(name)
    for feature in getattr(origin, "OriginFeatures", []) or []:
        role = str(getattr(feature, "Role", ""))
        label = str(getattr(feature, "Label", ""))
        obj_name = str(getattr(feature, "Name", ""))
        if role in variants or label in variants or obj_name in variants:
            return cast(object, feature)
    return None


def resolve_linksub(
    document: object,
    body: object | None,
    spec: str,
    *,
    sketch: object | None = None,
) -> object:
    if ":" in spec:
        object_name, sub_name = spec.split(":", 1)
        obj = lookup_object(document, object_name)
        if obj is None:
            raise LookupError(f"Reference object not found: {object_name}")
        return (obj, [sub_name])
    if sketch is not None and spec in {"H_Axis", "V_Axis"}:
        return (sketch, [spec])
    doc_axis = getattr(document, spec, None)
    if doc_axis is not None and spec.endswith("_Axis"):
        return (doc_axis, [""])
    for container in (body, document):
        if container is None:
            continue
        obj = _origin_feature(container, spec)
        if obj is not None:
            return (obj, [""])
    obj = lookup_object(document, spec)
    if obj is not None:
        return (obj, [""])
    raise LookupError(f"Reference not found: {spec}")


def resolve_revolve_axis(
    document: object,
    body: object | None,
    sketch: object,
    spec: str,
) -> object:
    """Resolve revolution axes the way PartDesign tests do for sketch profiles."""

    if spec in {"X_Axis", "Y_Axis", "Z_Axis"} and sketch is not None:
        sketch_axis = {"X_Axis": "V_Axis", "Y_Axis": "H_Axis", "Z_Axis": "V_Axis"}.get(spec)
        if sketch_axis is not None:
            return (sketch, [sketch_axis])
    return resolve_linksub(document, body, spec, sketch=sketch)


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
    "FeatureLike",
    "MutableFeatureLike",
    "bool_value",
    "count_value",
    "create_feature",
    "find_owning_body",
    "is_derived_from",
    "is_read_only_property",
    "lookup_object",
    "nonempty_string",
    "number_value",
    "optional_name",
    "require_absent",
    "require_body",
    "require_nonempty_shape",
    "require_object",
    "resolve_linksub",
    "resolve_revolve_axis",
    "resolve_optional_body",
    "set_attr",
    "set_feature_bool",
    "set_named_property",
    "set_originals",
    "set_tip",
    "string_list",
]
