"""Register Phase 7 / 7D tool modules on the MCP server."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from types import ModuleType
from typing import TYPE_CHECKING, Any

from ..instrumented_server import InstrumentedFastMCP
from ..server_state import ServerState
from ..tools_register_order import (
    REGISTER_TOOL_MODULE_OBJECTS,
    REGISTER_TOOL_MODULES,
)

if TYPE_CHECKING:
    from ..lease_manager import StaleLeaseRecoveryOrchestrator


def register_tool_modules(
    mcp: InstrumentedFastMCP,
    *,
    modules: Sequence[ModuleType] | None = None,
    module_names: Sequence[str] | None = None,
    state: ServerState,
    get_freecad_connection: Callable[[], Any],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    document_selector_input: type,
) -> dict[str, object]:
    if modules is not None and module_names is not None:
        raise TypeError("pass modules or module_names, not both")
    if modules is None:
        requested = REGISTER_TOOL_MODULES if module_names is None else module_names
        catalog = dict(
            zip(REGISTER_TOOL_MODULES, REGISTER_TOOL_MODULE_OBJECTS, strict=True)
        )
        try:
            modules = tuple(catalog[name] for name in requested)
        except KeyError as exc:
            raise ValueError(f"unknown tool module: {exc.args[0]}") from exc
    exports: dict[str, object] = {}
    for module in modules:
        module.DocumentSelectorInput = document_selector_input
        module_exports = module.register(
            mcp,
            state=state,
            get_freecad_connection=get_freecad_connection,
            stale_recovery=stale_recovery,
        )
        exports.update(module_exports)
    return exports
