"""Register Phase 7 / 7D tool modules on the MCP server."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from types import ModuleType
from typing import Any

from ..collaboration_client import _CONNECTION_METHODS, CollaborationClient
from ..instrumented_server import InstrumentedFastMCP
from ..server_state import ServerState
from ..tools_register_order import (
    REGISTER_TOOL_MODULE_OBJECTS,
    REGISTER_TOOL_MODULES,
)
from .tool_dependencies import ToolDependencies


def _lazy_collaboration_connection(
    get_freecad_connection: Callable[[], Any],
) -> Any:
    """Expose collaboration RPC methods without eager FreeCAD connect."""

    class _Accessor:
        __slots__ = ("_get_freecad_connection",)

        def __init__(self, getter: Callable[[], Any]) -> None:
            self._get_freecad_connection = getter

    accessor = _Accessor(get_freecad_connection)
    for method_name in _CONNECTION_METHODS:

        def _forward(
            self: _Accessor,
            *args: object,
            _method: str = method_name,
            **kwargs: object,
        ) -> object:
            return getattr(self._get_freecad_connection(), _method)(*args, **kwargs)

        setattr(_Accessor, method_name, _forward)
    return accessor


def _build_tool_dependencies(
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], Any],
    recovery_compatibility: Any,
    collaboration: CollaborationClient | None,
    document_selector_input: type,
) -> ToolDependencies:
    if collaboration is None:
        collaboration = CollaborationClient(
            _lazy_collaboration_connection(get_freecad_connection)
        )
    return ToolDependencies(
        state=state,
        get_freecad_connection=get_freecad_connection,
        recovery_compatibility=recovery_compatibility,
        collaboration=collaboration,
        document_selector_input=document_selector_input,
    )


def register_tool_modules(
    mcp: InstrumentedFastMCP,
    *,
    modules: Sequence[ModuleType] | None = None,
    module_names: Sequence[str] | None = None,
    state: ServerState,
    get_freecad_connection: Callable[[], Any],
    recovery_compatibility: Any,
    collaboration: CollaborationClient | None = None,
    document_selector_input: type,
) -> dict[str, object]:
    if modules is not None and module_names is not None:
        raise TypeError("pass modules or module_names, not both")
    if modules is not None or module_names is not None:
        if modules is None:
            requested = REGISTER_TOOL_MODULES if module_names is None else module_names
            catalog = dict(
                zip(REGISTER_TOOL_MODULES, REGISTER_TOOL_MODULE_OBJECTS, strict=True)
            )
            try:
                modules = tuple(catalog[name] for name in requested)
            except KeyError as exc:
                raise ValueError(f"unknown tool module: {exc.args[0]}") from exc
        dependencies = _build_tool_dependencies(
            state=state,
            get_freecad_connection=get_freecad_connection,
            recovery_compatibility=recovery_compatibility,
            collaboration=collaboration,
            document_selector_input=document_selector_input,
        )
        exports: dict[str, object] = {}
        for module in modules:
            module_exports = module.register(mcp, dependencies=dependencies)
            exports.update(module_exports)
        return exports

    from ..generated.capabilities.registration import register_tools

    dependencies = _build_tool_dependencies(
        state=state,
        get_freecad_connection=get_freecad_connection,
        recovery_compatibility=recovery_compatibility,
        collaboration=collaboration,
        document_selector_input=document_selector_input,
    )
    return register_tools(mcp, dependencies=dependencies)
