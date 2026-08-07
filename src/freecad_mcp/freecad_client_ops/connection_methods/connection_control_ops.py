"""Declarative shim — generated connection method lives in generated/capabilities."""

from freecad_mcp.generated.capabilities.connection_methods.connection_control_ops import (
    _authentication_required,
    _legacy_authority_removed,
    _validated_request_id,
    acknowledge_acquisition_claim,
    cancel_request,
    claim_acquisition_result,
    disconnect,
    get_request_status,
    heartbeat_document_locks_batch,
    notify_cancel_request,
    reconcile_document_lease,
)

__all__ = [
    '_authentication_required',
    '_legacy_authority_removed',
    '_validated_request_id',
    'acknowledge_acquisition_claim',
    'cancel_request',
    'claim_acquisition_result',
    'disconnect',
    'get_request_status',
    'heartbeat_document_locks_batch',
    'notify_cancel_request',
    'reconcile_document_lease',
]
