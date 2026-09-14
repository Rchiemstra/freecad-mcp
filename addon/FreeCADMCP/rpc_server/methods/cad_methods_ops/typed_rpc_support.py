"""Small typed helpers shared by native JSON-RPC mutation leaves."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Protocol, cast


def nonempty_string(value: object, field: str) -> str | None:
    """Return a stripped string, or ``None`` when the value is not usable."""

    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def optional_string(value: object) -> str | None:
    """Accept ``None`` or a nonempty string."""

    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def as_bool(value: object, default: bool) -> bool | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return None


def as_float(value: object, default: float | None = None) -> float | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def as_int(value: object, default: int | None = None) -> int | None:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


class _Invoker(Protocol):
    def __call__(self, *args: object, **kwargs: object) -> object: ...


def invoke(value: object, *args: object) -> object:
    if not callable(value):
        raise TypeError("value is not callable")
    return cast(_Invoker, value)(*args)


def call_named(owner: object, method: str, *args: object) -> object | None:
    func = getattr(owner, method, None)
    if func is None:
        return None
    return invoke(func, *args)


def assign_attr(item: object, name: str, value: object) -> None:
    setattr(item, name, value)


def require_object(
    document: object,
    name: str,
    *,
    missing_code: str,
    error: Callable[[str, str], BaseException],
) -> object:
    found = call_named(document, "getObject", name)
    if found is None:
        raise error(missing_code, f"Object not found: {name!r}")
    return found


def object_name(item: object) -> str:
    name = getattr(item, "Name", None)
    return name if isinstance(name, str) and name else ""


def object_label(item: object) -> str:
    label = getattr(item, "Label", None)
    if isinstance(label, str) and label:
        return label
    return object_name(item)


def object_type_id(item: object) -> str:
    type_id = getattr(item, "TypeId", None)
    return type_id if isinstance(type_id, str) else ""


def resolve_if_exists(
    document: object,
    name: str,
    if_exists: str,
    *,
    error: Callable[[str, str], BaseException],
) -> object | None:
    existing = call_named(document, "getObject", name)
    if existing is None:
        return None
    if if_exists == "skip":
        return existing
    if if_exists == "replace":
        call_named(document, "removeObject", object_name(existing) or name)
        return None
    raise error("OBJECT_ALREADY_EXISTS", f"Object already exists: {name!r}")


def add_named_object(document: object, type_id: str, name: str) -> object:
    created = call_named(document, "addObject", type_id, name)
    if created is None:
        raise RuntimeError(f"failed to create {type_id} {name!r}")
    return created


def add_to_container(container: object | None, item: object) -> None:
    if container is None:
        return
    adder = getattr(container, "addObject", None)
    if adder is not None:
        invoke(adder, item)
        return
    group = getattr(container, "Group", None)
    if isinstance(group, list) and item not in group:
        assign_attr(container, "Group", [*group, item])


def remove_from_container(container: object | None, item: object) -> None:
    if container is None:
        return
    remover = getattr(container, "removeObject", None)
    if remover is not None:
        try:
            invoke(remover, item)
            return
        except Exception:
            pass
    group = getattr(container, "Group", None)
    if isinstance(group, list):
        assign_attr(container, "Group", [member for member in group if member is not item])


def parse_ref(document: object, ref: str, error: Callable[[str, str], BaseException]) -> tuple[object, str]:
    if ":" in ref:
        name, sub = ref.split(":", 1)
    else:
        name, sub = ref, ""
    return require_object(document, name, missing_code="OBJECT_NOT_FOUND", error=error), sub


_SNAPSHOTS: list[object] = []


def snapshot_ring(document: object) -> list[object]:
    store = getattr(document, "_mcp_snapshots", None)
    if isinstance(store, list):
        return store
    try:
        module = importlib.import_module("FreeCAD")
    except Exception:
        module = None
    if module is not None:
        current = getattr(module, "_mcp_snapshots", None)
        if isinstance(current, list):
            return current
        try:
            setattr(module, "_mcp_snapshots", [])
            current = getattr(module, "_mcp_snapshots", None)
            if isinstance(current, list):
                return current
        except Exception:
            pass
    try:
        setattr(document, "_mcp_snapshots", [])
        store = getattr(document, "_mcp_snapshots", None)
        if isinstance(store, list):
            return store
    except Exception:
        pass
    return _SNAPSHOTS


__all__ = [
    "add_named_object",
    "add_to_container",
    "as_bool",
    "as_float",
    "as_int",
    "assign_attr",
    "call_named",
    "invoke",
    "nonempty_string",
    "object_label",
    "object_name",
    "object_type_id",
    "optional_string",
    "parse_ref",
    "remove_from_container",
    "require_object",
    "resolve_if_exists",
    "snapshot_ring",
]
