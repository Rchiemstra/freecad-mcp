"""Typed registration context for MCP tool modules (Phase 19)."""

from __future__ import annotations

from collections.abc import Callable, Iterator, MutableMapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from ..collaboration_client import CollaborationClient
    from ..freecad_client import FreeCADConnection
    from ..instrumented_server import InstrumentedFastMCP
    from ..server_state import ServerState


class ToolModuleRegister(Protocol):
    """Registration callable consumed by ``register_tool_modules``."""

    def __call__(
        self,
        mcp: InstrumentedFastMCP,
        *,
        dependencies: ToolDependencies,
    ) -> dict[str, object]:
        """Register tools on ``mcp`` and return export bindings."""


@dataclass(frozen=True, slots=True)
class ToolDependencies:
    """Explicit dependencies passed to every tool module at registration time."""

    state: ServerState
    get_freecad_connection: Callable[[], FreeCADConnection]
    recovery_compatibility: Any
    collaboration: CollaborationClient
    document_selector_input: type


@contextmanager
def module_document_selector(
    namespace: MutableMapping[str, object],
    selector: type,
) -> Iterator[None]:
    """Expose ``selector`` on ``module`` only while MCP evaluates annotations."""

    name = "DocumentSelectorInput"
    had_attr = name in namespace
    previous = namespace.get(name)
    namespace[name] = selector
    try:
        yield
    finally:
        if had_attr:
            namespace[name] = previous
        else:
            namespace.pop(name, None)


__all__ = [
    "ToolDependencies",
    "ToolModuleRegister",
    "module_document_selector",
]
