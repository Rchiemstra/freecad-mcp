"""Shared imports for dispatch helper modules."""

from __future__ import annotations

# ruff: noqa: E501, E701, E702, I001

import contextlib
import hmac
import os
import threading
import uuid

try:
    from document_state import document_modified_or_dirty, require_document_modified
except ImportError:
    from addon.FreeCADMCP.document_state import (
        document_modified_or_dirty,
        require_document_modified,
    )

try: from ....dispatch.gui_errors import GuiDispatchError, GuiDispatchTimeout; from ....dispatch.inflight_lease_credential import InflightLeaseCredential; from ....dispatch.request_cancellation_error import RequestCancellationError
except ImportError: from dispatch.gui_errors import GuiDispatchError, GuiDispatchTimeout; from dispatch.inflight_lease_credential import InflightLeaseCredential; from dispatch.request_cancellation_error import RequestCancellationError
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
from ...telemetry import emit as emit_telemetry

__all__ = [
    "DocumentHealthVerdict",
    "GuiDispatchError",
    "GuiDispatchTimeout",
    "GuiMutationTransaction",
    "InflightLeaseCredential",
    "RequestCancellationError",
    "RollbackCoverage",
    "RpcMutationKind",
    "ValidationProfile",
    "calculate_document_health_delta",
    "capture_document_health",
    "contextlib",
    "document_modified_or_dirty",
    "emit_telemetry",
    "hmac",
    "make_method_spec",
    "os",
    "require_document_modified",
    "threading",
    "uuid",
    "validate_document_invariants",
]
