"""Lease RPC methods extracted from ``FreeCADRPC`` (Phase 4 slice 4E)."""


from ._common import _rpc_mod


def lease_heartbeat_batch(self, leases, client_monotonic_ns=""):
    """Renew a batch on the reserved control lane; state remains server-owned."""
    if _rpc_mod().document_lease_service is None:
        return {
            "success": False,
            "error_code": "LEASE_PROTOCOL_UNAVAILABLE",
            "error": "Document lease v2 is not initialized",
        }
    identity = _rpc_mod()._import_document_lock().get_request_identity()
    results = []
    for item in leases if isinstance(leases, list) else []:
        session_uuid = (
            item.get("document_session_uuid") if isinstance(item, dict) else ""
        )
        try:
            credential = _rpc_mod()._credential_from_wire(item)
            status = _rpc_mod().document_lease_service.heartbeat(
                credential,
                current_operation=(
                    _rpc_mod()._redact_rpc_diagnostic(
                        item.get("current_operation"), identity=identity
                    )
                    or None
                ),
            )
            status["success"] = True
            results.append(status)
        except Exception as exc:
            failed = _rpc_mod()._lease_service_error(
                exc, request_id=identity.get("request_id")
            )
            failed["document_session_uuid"] = session_uuid
            failed["revoked"] = getattr(exc, "code", "") in {
                "LEASE_AUTHORIZATION_FAILED",
                "LEASE_STATE_FORBIDS_OPERATION",
            }
            results.append(failed)
    return {"success": True, "leases": results}
