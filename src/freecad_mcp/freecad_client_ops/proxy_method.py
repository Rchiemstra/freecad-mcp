"""Dotted JSON-RPC method bound to one serialized transport lane."""

from __future__ import annotations

from typing import Any


class ProxyMethod:
    """Dotted JSON-RPC method bound to one serialized transport lane."""

    def __init__(self, lane: Any, name: str):
        self._lane = lane
        self._name = name

    def __getattr__(self, name: str) -> ProxyMethod:
        return type(self)(self._lane, f"{self._name}.{name}")

    def __call__(self, *args: Any) -> Any:
        return self._lane.call(self._name, *args)
