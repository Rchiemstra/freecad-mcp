from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_facade_namespaces: list[Mapping[str, Any]] = []


def bind_facade_namespace(namespace: Mapping[str, Any]) -> None:
    """Bind the compatibility facade without consulting the module registry."""

    if not isinstance(namespace, Mapping):
        raise TypeError("namespace must be a mapping")
    if not any(existing is namespace for existing in _facade_namespaces):
        _facade_namespaces.append(namespace)


def facade_callable(name: str, default: Any) -> Any:
    for namespace in reversed(_facade_namespaces):
        candidate = namespace.get(name)
        if callable(candidate) and candidate is not default:
            return candidate
    return default


def facade_attr(name: str) -> Any | None:
    for namespace in reversed(_facade_namespaces):
        candidate = namespace.get(name)
        if candidate is not None:
            return candidate
    return None
