"""Discover typed RPC handlers registered by ``cad_methods_ops`` leaf modules."""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable
from types import ModuleType

_HANDLER_SYMBOL = "TYPED_RPC_HANDLER"


def _load_sibling_modules(package: ModuleType) -> list[ModuleType]:
    if package.__path__ is None:
        return []
    modules: list[ModuleType] = []
    for info in pkgutil.iter_modules(package.__path__):
        if info.ispkg:
            continue
        modules.append(importlib.import_module(f"{package.__name__}.{info.name}"))
    return modules


def discover_typed_rpc_handlers(
    package: ModuleType | None = None,
) -> dict[str, Callable[..., object]]:
    """Import sibling modules and collect ``TYPED_RPC_HANDLER`` registrations."""

    if package is None:
        package = importlib.import_module(__name__.rsplit(".", 1)[0])

    handlers: dict[str, Callable[..., object]] = {}
    for module in _load_sibling_modules(package):
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


def bind_typed_rpc_handlers(
    namespace: dict[str, object],
    handlers: dict[str, Callable[..., object]] | None = None,
) -> tuple[str, ...]:
    """Publish discovered handlers and return the bound method names."""

    if handlers is None:
        handlers = discover_typed_rpc_handlers()
    namespace.update(handlers)
    return tuple(sorted(handlers))
