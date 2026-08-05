"""Shared imports for rpc helper modules."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("FreeCADMCP.rpc_server")


@dataclass(frozen=True, slots=True)
class RpcHelperDependencies:
    """Explicit services and callbacks used by legacy helper façades."""

    document_identity_service: Any | None
    document_lease_service: Any | None
    worker_manager: Any | None
    logger: Any
    import_document_lock: Callable[[], Any]
    import_document_lease: Callable[[], Any]
    ensure_v2_document: Callable[[Any], Any]
    refresh_lock_indicator: Callable[[], Any]


__all__ = ["RpcHelperDependencies", "logger"]


