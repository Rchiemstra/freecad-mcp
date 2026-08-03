"""Shared imports for dispatch helper modules."""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import os
import threading
import uuid
from typing import Any

try:
    from document_state import document_modified_or_dirty, require_document_modified
except ImportError:
    from addon.FreeCADMCP.document_state import (
        document_modified_or_dirty,
        require_document_modified,
    )

from ...gui_dispatcher import GuiDispatchError, GuiDispatchTimeout
from ...handoff_continuations import HandoffContinuationStore
from ...inflight_requests import InflightLeaseCredential, RequestCancellationError
from ...lease_runtime import _import_document_lease, _import_document_lock
from ...mutation_guard import (
    DocumentHealthVerdict,
    GuiMutationTransaction,
    RollbackCoverage,
    RpcMutationKind,
    ValidationProfile,
    calculate_document_health_delta,
    capture_document_health,
    make_method_spec,
    validate_document_invariants,
)
from ...settings import load_settings
from ...snapshot_service import (
    create_lease_baseline_snapshot_gui,
    discard_lease_baseline_snapshot,
)
from ...telemetry import emit as emit_telemetry
from ._common import _rpc_mod, logger

try:
    from ...._shared.protocol.public_error import (
        public_error as lease_protocol_public_error,
    )
    from ...._shared.protocol.redaction import (
        redact_sensitive as redact_lease_protocol_details,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.public_error import public_error as lease_protocol_public_error
    from _shared.protocol.redaction import (
        redact_sensitive as redact_lease_protocol_details,
    )


class _FreeCADProxy:
    """Resolve ``FreeCAD`` via ``rpc_server`` so tests can monkeypatch it."""

    def __getattr__(self, name: str) -> Any:
        return getattr(_rpc_mod().FreeCAD, name)


FreeCAD = _FreeCADProxy()

__all__ = [
    "Any",
    "DocumentHealthVerdict",
    "FreeCAD",
    "GuiDispatchError",
    "GuiDispatchTimeout",
    "GuiMutationTransaction",
    "HandoffContinuationStore",
    "InflightLeaseCredential",
    "RequestCancellationError",
    "RollbackCoverage",
    "RpcMutationKind",
    "ValidationProfile",
    "_import_document_lease",
    "_import_document_lock",
    "_rpc_mod",
    "calculate_document_health_delta",
    "capture_document_health",
    "contextlib",
    "create_lease_baseline_snapshot_gui",
    "discard_lease_baseline_snapshot",
    "document_modified_or_dirty",
    "emit_telemetry",
    "hashlib",
    "hmac",
    "lease_protocol_public_error",
    "load_settings",
    "logger",
    "make_method_spec",
    "os",
    "redact_lease_protocol_details",
    "require_document_modified",
    "threading",
    "uuid",
    "validate_document_invariants",
]
