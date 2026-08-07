"""Declarative shim — generated connection method lives in generated/capabilities."""

from freecad_mcp.generated.capabilities.connection_methods.connection_stale_ops import (
    _handle_stale_rpc_refusal,
    _legacy_authority_removed,
    _maybe_recover_stale_before_protected_rpc,
    _reconcile_stale_session,
    _retryable_stale_recovery_response,
    stale_recovery_status,
)

__all__ = [
    '_handle_stale_rpc_refusal',
    '_legacy_authority_removed',
    '_maybe_recover_stale_before_protected_rpc',
    '_reconcile_stale_session',
    '_retryable_stale_recovery_response',
    'stale_recovery_status',
]
