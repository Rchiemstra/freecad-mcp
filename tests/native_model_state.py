"""Stable document model-state oracle for native qualification tests."""

from __future__ import annotations

import hashlib

# dumpPropertyContent for these properties varies across rollback even when restored.
_UNSTABLE_DUMP_PROPERTIES = frozenset({"ExpressionEngine"})


def _expression_engine_fingerprint(item: object, name: str) -> tuple[tuple[str, str], ...] | None:
    engine = getattr(item, name, None)
    if not engine:
        return None
    bindings: list[tuple[str, str]] = []
    for entry in engine:
        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
            bindings.append((str(entry[0]), str(entry[1])))
        else:
            bindings.append((str(entry), ""))
    if not bindings:
        return None
    return tuple(sorted(bindings))


def property_content(item: object, name: str) -> str | tuple[tuple[str, str], ...] | None:
    if name == "Proxy":
        proxy = getattr(item, "Proxy", None)
        if proxy is None:
            return None
        return f"{type(proxy).__module__}.{type(proxy).__qualname__}"
    if name in _UNSTABLE_DUMP_PROPERTIES:
        return _expression_engine_fingerprint(item, name)
    dumped = bytes(item.dumpPropertyContent(name, 0))
    return hashlib.sha256(dumped).hexdigest()


def model_state(document: object) -> tuple:
    objects = getattr(document, "Objects", ())
    return tuple(
        (
            item.Name,
            item.TypeId,
            tuple(item.State),
            tuple(sorted(obj.Name for obj in item.InList)),
            tuple(sorted(obj.Name for obj in item.OutList)),
            tuple(
                (
                    name,
                    item.getTypeIdOfProperty(name),
                    item.getGroupOfProperty(name),
                    tuple(item.getPropertyStatus(name)),
                    property_content(item, name),
                )
                for name in sorted(item.PropertiesList)
            ),
        )
        for item in objects
    )
