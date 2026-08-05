"""Frozen public shims for removed MCP document-lease authority."""

from __future__ import annotations

from .lease_manager_ops.lease_client_manager import LeaseClientManager
from .lease_manager_ops.lease_compatibility_result import LeaseCompatibilityResult
from .lease_manager_ops.native_session_handle import NativeSessionHandle
from .lease_manager_ops.stale_lease_recovery_orchestrator import (
    StaleLeaseRecoveryOrchestrator,
)

__all__ = [
    "LeaseClientManager",
    "LeaseCompatibilityResult",
    "NativeSessionHandle",
    "StaleLeaseRecoveryOrchestrator",
]
