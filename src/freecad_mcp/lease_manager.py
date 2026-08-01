"""MCP-side custody for document lease credentials.

Raw lease tokens deliberately live only in this module's in-memory records and
in the short-lived wire dictionaries produced for authenticated RPC calls.
Public status, reprs, and revocation records are always redacted.
"""

from __future__ import annotations

# §3.3 compatibility shims — keep old import paths working.
from .lease_manager_ops.canonicalize import canonicalize_document_path
from .lease_manager_ops.heartbeat_helpers import (
    extract_active_sessions_from_heartbeat,
    extract_stale_sessions_from_heartbeat,
    heartbeat_item_confirms_active_lease,
    heartbeat_item_lease_state,
    is_timeout_stale_heartbeat_item,
)
from .lease_manager_ops.lease_alias_conflict_error import LeaseAliasConflictError
from .lease_manager_ops.lease_client_manager import LeaseClientManager
from .lease_manager_ops.lease_credential import LeaseCredential
from .lease_manager_ops.lease_manager_closed_error import LeaseManagerClosedError
from .lease_manager_ops.lease_manager_disconnected_error import LeaseManagerDisconnectedError
from .lease_manager_ops.lease_manager_error import LeaseManagerError
from .lease_manager_ops.lease_not_found_error import LeaseNotFoundError
from .lease_manager_ops.lease_revocation import LeaseRevocation
from .lease_manager_ops.rpc_request_context import RpcRequestContext
from .lease_manager_ops.stale_lease_recovery_orchestrator import StaleLeaseRecoveryOrchestrator
from .lease_manager_ops.stale_recovery_constants import (
    DEFAULT_STALE_AFTER_SECONDS,
    REVOCATION_ERROR_CODES,
    STALE_RECOVERY_EXEMPT_RPC_METHODS,
    STALE_RECOVERY_OUTCOME_RECOVERED,
    STALE_RECOVERY_OUTCOME_REFUSED_RETRYABLE,
    STALE_RECOVERY_OUTCOME_REFUSED_TERMINAL,
    STALE_RECOVERY_OUTCOME_SKIPPED_BACKOFF,
    STALE_RECOVERY_OUTCOME_SKIPPED_TERMINAL,
    STALE_RECOVERY_OUTCOME_SKIPPED_UNNECESSARY,
    STALE_RECOVERY_RETRY_ERROR_CODE,
    STALE_RECOVERY_TRIGGER_HEARTBEAT,
    STALE_RECOVERY_TRIGGER_POST_TOOL,
    STALE_RECOVERY_TRIGGER_PRE_OPERATION,
    STALE_RECOVERY_TRIGGER_RPC_REFUSAL,
)
from .lease_manager_ops.stale_recovery_helpers import (
    reconcile_refusal_is_terminal,
    reconcile_response_is_idempotent,
    rpc_response_indicates_stale_refusal,
    rpc_response_mutation_may_have_begun,
    stale_recovery_result_to_dict,
    summarize_stale_recovery_results,
)
from .lease_manager_ops.stale_recovery_result import StaleRecoveryResult

__all__ = [
    "DEFAULT_STALE_AFTER_SECONDS",
    "REVOCATION_ERROR_CODES",
    "STALE_RECOVERY_EXEMPT_RPC_METHODS",
    "STALE_RECOVERY_OUTCOME_RECOVERED",
    "STALE_RECOVERY_OUTCOME_REFUSED_RETRYABLE",
    "STALE_RECOVERY_OUTCOME_REFUSED_TERMINAL",
    "STALE_RECOVERY_OUTCOME_SKIPPED_BACKOFF",
    "STALE_RECOVERY_OUTCOME_SKIPPED_TERMINAL",
    "STALE_RECOVERY_OUTCOME_SKIPPED_UNNECESSARY",
    "STALE_RECOVERY_RETRY_ERROR_CODE",
    "STALE_RECOVERY_TRIGGER_HEARTBEAT",
    "STALE_RECOVERY_TRIGGER_POST_TOOL",
    "STALE_RECOVERY_TRIGGER_PRE_OPERATION",
    "STALE_RECOVERY_TRIGGER_RPC_REFUSAL",
    "LeaseAliasConflictError",
    "LeaseClientManager",
    "LeaseCredential",
    "LeaseManagerClosedError",
    "LeaseManagerDisconnectedError",
    "LeaseManagerError",
    "LeaseNotFoundError",
    "LeaseRevocation",
    "RpcRequestContext",
    "StaleLeaseRecoveryOrchestrator",
    "StaleRecoveryResult",
    "canonicalize_document_path",
    "extract_active_sessions_from_heartbeat",
    "extract_stale_sessions_from_heartbeat",
    "heartbeat_item_confirms_active_lease",
    "heartbeat_item_lease_state",
    "is_timeout_stale_heartbeat_item",
    "reconcile_refusal_is_terminal",
    "reconcile_response_is_idempotent",
    "rpc_response_indicates_stale_refusal",
    "rpc_response_mutation_may_have_begun",
    "stale_recovery_result_to_dict",
    "summarize_stale_recovery_results",
]
