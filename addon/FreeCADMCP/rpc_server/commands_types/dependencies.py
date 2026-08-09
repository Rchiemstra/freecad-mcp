"""Typed collaborators for workbench command instances."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CommandDependencies:
    freecad: Any
    load_settings: Callable[[], dict[str, Any]]
    save_settings: Callable[[dict[str, Any]], Any]
    start_rpc_server: Callable[[], str]
    stop_rpc_server: Callable[[], str]
    runtime_running: Callable[[], bool]


_default_dependencies: CommandDependencies | None = None


def bind_command_dependencies(dependencies: CommandDependencies) -> None:
    global _default_dependencies
    if not isinstance(dependencies, CommandDependencies):
        raise TypeError("dependencies must be CommandDependencies")
    _default_dependencies = dependencies


def current_command_dependencies() -> CommandDependencies:
    if _default_dependencies is None:
        raise RuntimeError("command dependencies are not initialized")
    return _default_dependencies
