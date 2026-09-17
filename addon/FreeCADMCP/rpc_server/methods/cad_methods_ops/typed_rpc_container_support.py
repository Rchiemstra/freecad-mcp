"""Container and snapshot helpers for typed native JSON-RPC mutations."""

from __future__ import annotations

from .typed_rpc_support import assign_attr, call_named, invoke
from .typed_runtime import TypedMutationError, load_module


def _group_members(group: object) -> list[object]:
    if isinstance(group, list):
        return list(group)
    if isinstance(group, tuple):
        return list(group)
    return []


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
        try:
            invoke(adder, item)
            return
        except Exception:
            pass
    group = getattr(container, "Group", None)
    members = _group_members(group)
    if item not in members:
        assign_attr(container, "Group", [*members, item])


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
    members = _group_members(group)
    if members:
        assign_attr(container, "Group", [member for member in members if member is not item])


_SNAPSHOTS: list[object] = []


def _module_snapshot_ring() -> list[object] | None:
    """Historical live store shared with snapshot_gui / execute_code."""

    try:
        freecad = load_module("FreeCAD")
    except (TypedMutationError, ImportError):
        return None
    current = getattr(freecad, "_mcp_snapshots", None)
    if isinstance(current, list):
        return current
    try:
        setattr(freecad, "_mcp_snapshots", [])
        current = getattr(freecad, "_mcp_snapshots", None)
        if isinstance(current, list):
            return current
    except Exception:
        return None
    return None


def snapshot_rings(document: object) -> tuple[list[object], ...]:
    """Every live snapshot ring that restore must search.

    Unit tests seed ``document._mcp_snapshots``. Live FreeCAD keeps the same
    identities on ``FreeCAD._mcp_snapshots``. Searching both keeps both.
    """

    rings: list[list[object]] = []
    document_store = getattr(document, "_mcp_snapshots", None)
    if isinstance(document_store, list):
        rings.append(document_store)
    module_ring = _module_snapshot_ring()
    if module_ring is not None and module_ring not in rings:
        rings.append(module_ring)
    if rings:
        return tuple(rings)
    try:
        setattr(document, "_mcp_snapshots", [])
        store = getattr(document, "_mcp_snapshots", None)
        if isinstance(store, list):
            return (store,)
    except Exception:
        pass
    return (_SNAPSHOTS,)


def snapshot_ring(document: object) -> list[object]:
    return snapshot_rings(document)[0]


__all__ = [
    "add_named_object",
    "add_to_container",
    "remove_from_container",
    "snapshot_ring",
    "snapshot_rings",
]
