"""Container and snapshot helpers for typed native JSON-RPC mutations."""

from __future__ import annotations

from .typed_rpc_support import assign_attr, call_named, invoke


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


def snapshot_ring(document: object) -> list[object]:
    store = getattr(document, "_mcp_snapshots", None)
    if isinstance(store, list):
        return store
    try:
        import FreeCAD
    except ImportError:
        FreeCAD = None  # type: ignore[misc, assignment]
    if FreeCAD is not None:
        current = getattr(FreeCAD, "_mcp_snapshots", None)
        if isinstance(current, list):
            return current
        try:
            setattr(FreeCAD, "_mcp_snapshots", [])
            current = getattr(FreeCAD, "_mcp_snapshots", None)
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
    "remove_from_container",
    "snapshot_ring",
]
