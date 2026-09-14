"""Stable document model-state oracle for native qualification tests."""

from __future__ import annotations

import hashlib

# dumpPropertyContent for these properties varies across rollback even when restored.
_UNSTABLE_DUMP_PROPERTIES = frozenset({"ExpressionEngine"})

# Object.State flags that are execution bookkeeping, not durable model content.
_TRANSIENT_STATE_FLAGS = frozenset({"Touched"})

# Unnamed locker bits that flap on rollback (e.g. Body.Group User3); keep schema flags.
_TRANSIENT_PROPERTY_STATUS_BITS = frozenset({15, 18, 29, 30, 31})


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


def _stable_state(item: object) -> tuple[str, ...]:
    state = getattr(item, "State", ())
    if not isinstance(state, (list, tuple)):
        return ()
    return tuple(sorted(str(flag) for flag in state if str(flag) not in _TRANSIENT_STATE_FLAGS))


def _stable_property_status(item: object, name: str) -> tuple:
    status = tuple(item.getPropertyStatus(name))
    filtered: list[object] = []
    for flag in status:
        if isinstance(flag, int) and flag in _TRANSIENT_PROPERTY_STATUS_BITS:
            continue
        filtered.append(flag)
    return tuple(filtered)


def model_state(document: object) -> tuple:
    objects = getattr(document, "Objects", ())
    return tuple(
        (
            item.Name,
            item.TypeId,
            _stable_state(item),
            tuple(sorted(obj.Name for obj in item.InList)),
            tuple(sorted(obj.Name for obj in item.OutList)),
            tuple(
                (
                    name,
                    item.getTypeIdOfProperty(name),
                    item.getGroupOfProperty(name),
                    _stable_property_status(item, name),
                    property_content(item, name),
                )
                for name in sorted(item.PropertiesList)
            ),
        )
        for item in objects
    )
