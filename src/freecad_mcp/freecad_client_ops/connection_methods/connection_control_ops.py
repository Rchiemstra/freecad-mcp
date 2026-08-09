"""Declarative shim — generated connection method lives in generated/capabilities."""

from freecad_mcp.generated.capabilities.connection_methods import (
    connection_control_ops as _generated,
)

heartbeat_document_locks_batch = _generated.heartbeat_document_locks_batch
reconcile_document_lease = _generated.reconcile_document_lease
get_request_status = _generated.get_request_status
claim_acquisition_result = _generated.claim_acquisition_result
acknowledge_acquisition_claim = _generated.acknowledge_acquisition_claim
cancel_request = _generated.cancel_request
notify_cancel_request = _generated.notify_cancel_request
disconnect = _generated.disconnect
_validated_request_id = _generated._validated_request_id
_authentication_required = _generated._authentication_required
_legacy_authority_removed = _generated._legacy_authority_removed

__all__ = [  # noqa: RUF022
    'heartbeat_document_locks_batch',
    'reconcile_document_lease',
    'get_request_status',
    'claim_acquisition_result',
    'acknowledge_acquisition_claim',
    'cancel_request',
    'notify_cancel_request',
    'disconnect',
    '_validated_request_id',
    '_authentication_required',
    '_legacy_authority_removed',
]
