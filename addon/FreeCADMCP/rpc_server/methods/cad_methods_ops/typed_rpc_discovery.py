"""Discover typed RPC handlers registered by ``cad_methods_ops`` leaf modules."""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

from . import typed_rpc_handler_modules

_HANDLER_SYMBOL = "TYPED_RPC_HANDLER"


def _collect_handlers(modules: tuple[ModuleType, ...]) -> dict[str, Callable[..., object]]:
    handlers: dict[str, Callable[..., object]] = {}
    for module in modules:
        registration = getattr(module, _HANDLER_SYMBOL, None)
        if registration is None:
            continue
        if not (isinstance(registration, tuple) and len(registration) == 2):
            raise TypeError(
                f"{module.__name__}.{_HANDLER_SYMBOL} must be a (method_name, handler) tuple"
            )
        method_name, handler = registration
        if not isinstance(method_name, str) or not callable(handler):
            raise TypeError(
                f"{module.__name__}.{_HANDLER_SYMBOL} must register a str name and callable handler"
            )
        if method_name in handlers:
            raise ValueError(f"duplicate typed RPC handler: {method_name}")
        handlers[method_name] = handler
    return handlers


def discover_typed_rpc_handlers(
    package: ModuleType | None = None,
) -> dict[str, Callable[..., object]]:
    """Collect ``TYPED_RPC_HANDLER`` registrations from statically imported leaf modules."""

    del package  # static discovery ignores dynamic package scans
    return _collect_handlers(typed_rpc_handler_modules._HANDLER_MODULES)


def bind_typed_rpc_handlers(
    namespace: dict[str, object],
    handlers: dict[str, Callable[..., object]] | None = None,
) -> tuple[str, ...]:
    """Publish discovered handlers and return the bound method names."""

    if handlers is None:
        handlers = discover_typed_rpc_handlers()
    namespace.update(handlers)
    return tuple(sorted(handlers))
