"""Stale recovery and revocation constants."""

from __future__ import annotations

_REVOCATION_ERROR_CODES = frozenset(
    {
        "LEASE_REVOKED",
        "USER_INTERVENED",
        "LEASE_GENERATION_MISMATCH",
        "LEASE_TOKEN_MISMATCH",
        "TOKEN_MISMATCH",
    }
)

# Public alias for regression tests; STALE must never appear here.
REVOCATION_ERROR_CODES = _REVOCATION_ERROR_CODES

DEFAULT_STALE_AFTER_SECONDS = 90.0

# D8: stable orchestration reason codes (token-free).
STALE_RECOVERY_TRIGGER_HEARTBEAT = "heartbeat_stale_observed"
STALE_RECOVERY_TRIGGER_POST_TOOL = "post_tool_exceeded_stale_threshold"
STALE_RECOVERY_TRIGGER_PRE_OPERATION = "pre_operation_lazy"
STALE_RECOVERY_TRIGGER_RPC_REFUSAL = "rpc_stale_refusal"

STALE_RECOVERY_OUTCOME_RECOVERED = "recovered"
STALE_RECOVERY_OUTCOME_REFUSED_RETRYABLE = "refused_retryable"
STALE_RECOVERY_OUTCOME_REFUSED_TERMINAL = "refused_terminal"
STALE_RECOVERY_OUTCOME_SKIPPED_BACKOFF = "skipped_backoff"
STALE_RECOVERY_OUTCOME_SKIPPED_TERMINAL = "skipped_terminal"
STALE_RECOVERY_OUTCOME_SKIPPED_UNNECESSARY = "skipped_unnecessary"

STALE_RECOVERY_RETRY_ERROR_CODE = "LEASE_STALE_RECOVERED_RETRY"

STALE_RECOVERY_EXEMPT_RPC_METHODS = frozenset(
    {
        "lease_heartbeat_batch",
        "lease_reconcile",
        "handshake_v2",
        "get_request_status",
        "claim_acquisition_result",
        "cancel_request",
    }
)

_TERMINAL_RECONCILE_ERROR_CODES = frozenset(
    {
        "LEASE_AUTHORIZATION_FAILED",
        "LIVE_DOCUMENT_VALIDATION_FAILED",
        "LEASE_COORDINATION_LOST",
    }
)

_RECOVERY_BACKOFF_BASE_S = 2.0
_RECOVERY_BACKOFF_CAP_S = 60.0
_RECOVERY_BLOCKING_TIMEOUT_S = 120.0


def _upper_state(value: object) -> str:
    return str(value or "").strip().upper()
