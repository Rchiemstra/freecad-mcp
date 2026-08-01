from __future__ import annotations

# ruff: noqa: F403, F405
from ._support import *

"""Inflight lease credential retention."""

def model_credential(inflight_credential):
    lease = _import_document_lease()
    return lease.LeaseCredential(
        lease_id=inflight_credential.lease_id,
        document_session_uuid=inflight_credential.document_session_uuid,
        generation=inflight_credential.generation,
        token=inflight_credential.token,
        mcp_instance_id=inflight_credential.mcp_instance_id,
    )


def retain_inflight_credential(self, credential):
    """Retain a credential created mid-request until actual completion."""

    inflight = self._current_inflight()
    if inflight is None:
        return
    inflight.add_credentials(
        (
            InflightLeaseCredential(
                lease_id=credential.lease_id,
                document_session_uuid=credential.document_session_uuid,
                generation=credential.generation,
                token=credential.token,
                mcp_instance_id=credential.mcp_instance_id,
            ),
        )
    )
    inflight.touch_credentials(
        (
            InflightLeaseCredential(
                lease_id=credential.lease_id,
                document_session_uuid=credential.document_session_uuid,
                generation=credential.generation,
                token=credential.token,
                mcp_instance_id=credential.mcp_instance_id,
            ),
        )
    )


def touch_inflight_credential(self, credential, inflight=None):
    inflight = inflight or self._current_inflight()
    if inflight is None:
        return
    inflight.touch_credentials(
        (
            InflightLeaseCredential(
                lease_id=credential.lease_id,
                document_session_uuid=credential.document_session_uuid,
                generation=credential.generation,
                token=credential.token,
                mcp_instance_id=credential.mcp_instance_id,
            ),
        )
    )
    if _rpc_mod().rpc_acquisition_claim_store is not None:
        try:
            identity = _import_document_lock().get_request_identity()
            _rpc_mod().rpc_acquisition_claim_store.acknowledge_credential(
                mcp_runtime_id=str(
                    identity.get("instance_id")
                    or getattr(credential, "mcp_instance_id", "")
                    or ""
                ),
                lease_id=credential.lease_id,
                document_session_uuid=credential.document_session_uuid,
                generation=credential.generation,
                token=credential.token,
            )
        except Exception:
            _rpc_mod().logger.debug(
                "acquisition claim auto-ack failed", exc_info=True
            )
