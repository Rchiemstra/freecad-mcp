"""Declarative shim — generated connection method lives in generated/capabilities."""

from freecad_mcp.generated.capabilities.connection_methods import (
    connection_stale_ops as _generated,
)

stale_recovery_status = _generated.stale_recovery_status
_reconcile_stale_session = _generated._reconcile_stale_session
_maybe_recover_stale_before_protected_rpc = _generated._maybe_recover_stale_before_protected_rpc
_retryable_stale_recovery_response = _generated._retryable_stale_recovery_response
_handle_stale_rpc_refusal = _generated._handle_stale_rpc_refusal
_legacy_authority_removed = _generated._legacy_authority_removed

__all__ = [  # noqa: RUF022
    'stale_recovery_status',
    '_reconcile_stale_session',
    '_maybe_recover_stale_before_protected_rpc',
    '_retryable_stale_recovery_response',
    '_handle_stale_rpc_refusal',
    '_legacy_authority_removed',
]
