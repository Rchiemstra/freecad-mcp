"""Lookup and resolution helpers for typed PartDesign / Part feature mutations."""

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


__all__ = [
    "FeatureLike",
    "MutableFeatureLike",
    "find_owning_body",
    "is_derived_from",
    "lookup_object",
    "require_absent",
    "require_body",
    "require_object",
    "resolve_linksub",
    "resolve_revolve_axis",
    "resolve_optional_body",
]
