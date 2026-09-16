"""Narrow document helpers for typed CAD apply/inspect callbacks."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Protocol, cast


class _DocumentMethod(Protocol):
    def __call__(self, *args: object) -> object: ...


def require_callable(document: object, name: str) -> _DocumentMethod:
    attribute = getattr(document, name, None)
    if not callable(attribute):
        raise AttributeError(f"document is missing callable {name}")
    return cast(_DocumentMethod, attribute)


def document_name(document: object) -> str:
    name = getattr(document, "Name", None)
    if not isinstance(name, str) or not name.strip():
        raise AttributeError("document is missing a nonempty Name")
    return name


def get_object(document: object, name: str) -> object | None:
    getter = require_callable(document, "getObject")
    return getter(name)


def add_object(document: object, object_type: str, name: str) -> object:
    created = require_callable(document, "addObject")(object_type, name)
    if created is None:
        raise RuntimeError(f"addObject returned no object for {name!r}")
    return created


def remove_object(document: object, name: str) -> None:
    require_callable(document, "removeObject")(name)


def iter_objects(document: object) -> Iterator[object]:
    objects = getattr(document, "Objects", ())
    if objects is None:
        return
    yield from objects


def object_names(document: object) -> tuple[str, ...]:
    names: list[str] = []
    for item in iter_objects(document):
        name = getattr(item, "Name", None)
        if isinstance(name, str) and name.strip():
            names.append(name)
    return tuple(names)


def assign_properties(target: object, properties: Mapping[str, object]) -> None:
    for key, value in properties.items():
        if key in {"ShapeColor", "ViewObject"}:
            continue
        setattr(target, key, value)


__all__ = [
    "add_object",
    "assign_properties",
    "document_name",
    "get_object",
    "iter_objects",
    "object_names",
    "remove_object",
    "require_callable",
]
