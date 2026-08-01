"""Register Phase 7 / 7D tool modules on the MCP server."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Sequence
from typing import Any

from ..instrumented_server import InstrumentedFastMCP
from ..lease_manager import StaleLeaseRecoveryOrchestrator
from ..server_state import ServerState


def register_tool_modules(
    mcp: InstrumentedFastMCP,
    *,
    module_names: Sequence[str],
    state: ServerState,
    get_freecad_connection: Callable[[], Any],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    document_selector_input: type,
) -> dict[str, object]:
    exports: dict[str, object] = {}
    for module_name in module_names:
        module = importlib.import_module(f"freecad_mcp.{module_name}")
        module.DocumentSelectorInput = document_selector_input
        module_exports = module.register(
            mcp,
            state=state,
            get_freecad_connection=get_freecad_connection,
            stale_recovery=stale_recovery,
        )
        exports.update(module_exports)
    return exports
