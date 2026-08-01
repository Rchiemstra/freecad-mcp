"""Runtime service discovery and headless-safe notification queueing."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from typing import Any

from ._log import logger
from .events import ServiceProvider


def default_service_provider() -> Any | None:
    """Find the already-loaded RPC module without importing it eagerly."""

    candidates = (
        "rpc_server.rpc_server",
        "addon.FreeCADMCP.rpc_server.rpc_server",
    )
    for module_name in candidates:
        module = sys.modules.get(module_name)
        if module is not None:
            service = getattr(module, "document_lease_service", None)
            if service is not None:
                return service

    package = sys.modules.get("rpc_server")
    module = getattr(package, "rpc_server", None) if package is not None else None
    return getattr(module, "document_lease_service", None) if module else None


def get_runtime_service(provider: ServiceProvider | None = None) -> Any | None:
    """Return the current lease service, or ``None`` when RPC is not running."""

    from .. import observer as observer_mod

    try:
        return (provider or observer_mod._default_service_provider)()
    except Exception:
        logger.debug("lease service provider failed", exc_info=True)
        return None


def default_agent_mutation_checker(key: str) -> bool:
    """Delegate attribution to the legacy request-scoped mutation context."""

    module = sys.modules.get("document_lock") or sys.modules.get(
        "addon.FreeCADMCP.document_lock"
    )
    if module is None:
        try:
            module = importlib.import_module("document_lock")
        except Exception:
            try:
                module = importlib.import_module("addon.FreeCADMCP.document_lock")
            except Exception:
                return False
    checker = getattr(module, "is_agent_mutating", None)
    if not callable(checker):
        return False
    try:
        return bool(checker(key))
    except Exception:
        logger.debug("agent mutation attribution failed for %r", key, exc_info=True)
        return False


def is_internal_snapshot_save(document: Any, filename: Any) -> bool:
    """Recognize only the exact synchronous save callback of worker saveCopy."""

    module = sys.modules.get("document_lock") or sys.modules.get(
        "addon.FreeCADMCP.document_lock"
    )
    if module is None:
        return False
    checker = getattr(module, "is_internal_snapshot_save", None)
    if not callable(checker):
        return False
    try:
        return bool(checker(document, filename))
    except Exception:
        logger.debug("internal snapshot save attribution failed", exc_info=True)
        return False


def default_selected_document_provider() -> Any | None:
    module = sys.modules.get("FreeCAD")
    if module is None:
        try:
            module = importlib.import_module("FreeCAD")
        except Exception:
            return None
    return getattr(module, "ActiveDocument", None)


def qt_or_direct_queue(callback: Callable[[], None]) -> None:
    """Queue through Qt when available, with a headless-safe fallback."""

    qt_core = None
    for package_name in ("PySide", "PySide2", "PySide6"):
        try:
            package = importlib.import_module(package_name)
            qt_core = getattr(package, "QtCore", None)
            if qt_core is None:
                qt_core = importlib.import_module(f"{package_name}.QtCore")
            break
        except Exception:
            continue
    timer = getattr(qt_core, "QTimer", None) if qt_core is not None else None
    single_shot = getattr(timer, "singleShot", None) if timer is not None else None
    if callable(single_shot):
        single_shot(0, callback)
    else:
        callback()
