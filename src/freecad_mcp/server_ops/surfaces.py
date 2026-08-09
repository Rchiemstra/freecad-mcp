"""§3.3 monkeypatch surfaces for server bootstrap."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

DIAGNOSTIC_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


@dataclass(frozen=True, slots=True)
class ServerSurfaceBindings:
    """Providers owned by the server composition root."""

    state: Callable[[], Any]
    connection_lock: Any
    logger: Any
    get_freecad_connection: Callable[[], Any]
    authenticate_connection: Callable[..., Any]
    freecad_connection_factory: Callable[..., Any]
    emit_event: Callable[..., Any]


_bindings: ServerSurfaceBindings | None = None


def bind_server_surfaces(bindings: ServerSurfaceBindings) -> None:
    """Install the explicit server-root providers used by compatibility paths."""

    global _bindings
    if not isinstance(bindings, ServerSurfaceBindings):
        raise TypeError("server surface bindings must be ServerSurfaceBindings")
    _bindings = bindings


def _require_bindings() -> ServerSurfaceBindings:
    if _bindings is None:
        raise RuntimeError("server surfaces composition root is not initialized")
    return _bindings


def __getattr__(name: str):
    if name not in {
        "state",
        "connection_lock",
        "logger",
        "get_freecad_connection",
        "authenticate_connection",
        "freecad_connection_factory",
        "emit_event",
    }:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    bindings = _require_bindings()
    if name == "state":
        return bindings.state()
    if name == "connection_lock":
        return bindings.connection_lock
    if name == "logger":
        return bindings.logger
    if name == "get_freecad_connection":
        return bindings.get_freecad_connection
    if name == "authenticate_connection":
        return bindings.authenticate_connection
    if name == "freecad_connection_factory":
        return bindings.freecad_connection_factory
    if name == "emit_event":
        return bindings.emit_event
    raise AssertionError(f"unhandled server surface {name!r}")
