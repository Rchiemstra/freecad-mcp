from __future__ import annotations

import hmac
import os
from typing import Any

from .lease_record import LeaseRecord
from .lease_state import LeaseState
from .registry_state import _registry, _registry_lock
from .request_identity import get_request_identity
from .sidecar_io import _read_sidecar, sidecar_path_for


def _load_mutation_record(doc_key: str) -> LeaseRecord | None:
    with _registry_lock:
        record = _registry.get(doc_key)
    if record is not None:
        return record
    if not (os.path.isabs(doc_key) and doc_key.lower().endswith(".fcstd")):
        return None
    side = _read_sidecar(sidecar_path_for(doc_key))
    if not side:
        return None
    try:
        return LeaseRecord.from_dict(side)
    except TypeError:
        return None


def _mutation_state_error(record: LeaseRecord, allowed_states: set[str]) -> dict[str, Any] | None:
    if record.state == LeaseState.USER_INTERVENED.value:
        return {
            "success": False,
            "error_code": "user_intervened",
            "error": (
                "A user edited this document while the agent held the lease. "
                "The revoked agent may not automatically reacquire it."
            ),
            "lease": record.to_dict(),
        }
    if record.state not in allowed_states:
        return {
            "success": False,
            "error_code": "lease_state_blocks_mutation",
            "error": f"Lease state {record.state} does not permit this mutation",
            "lease": record.to_dict(),
        }
    return None


def _mutation_owner_error(
    record: LeaseRecord, instance_id: str | None
) -> dict[str, Any] | None:
    if instance_id and record.instance_id == instance_id:
        return None
    return {
        "success": False,
        "error_code": "document_locked_by_other",
        "error": (
            f"Document is locked by instance {record.instance_id} "
            f"(client={record.client!r}, pid={record.pid})"
        ),
        "lease": record.to_dict(),
    }


def _mutation_credential_error(
    record: LeaseRecord,
    identity: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    credentials = identity.get("lease_credentials") or []
    if not credentials:
        if identity.get("lease_id") and identity.get("lease_id") != record.lease_id:
            return (
                {
                    "success": False,
                    "error_code": "lease_id_mismatch",
                    "error": "Lease identifier does not match the active lease",
                    "lease": record.to_dict(),
                },
                None,
            )
        generation = identity.get("lease_generation")
        if generation is not None and int(generation) != record.generation:
            return (
                {
                    "success": False,
                    "error_code": "lease_generation_mismatch",
                    "error": "Lease generation has been fenced",
                    "lease": record.to_dict(),
                },
                None,
            )
        session_uuid = identity.get("document_session_uuid")
        if (
            session_uuid
            and record.document_session_uuid
            and session_uuid != record.document_session_uuid
        ):
            return (
                {
                    "success": False,
                    "error_code": "document_session_mismatch",
                    "error": "Document session identity does not match",
                    "lease": record.to_dict(),
                },
                None,
            )
        return None, identity.get("lease_token")

    matched = next(
        (
            item
            for item in credentials
            if isinstance(item, dict)
            and (
                item.get("lease_id") == record.lease_id
                or (
                    record.document_session_uuid
                    and item.get("document_session_uuid")
                    == record.document_session_uuid
                )
            )
        ),
        None,
    )
    if matched is None:
        return (
            {
                "success": False,
                "error_code": "lease_credential_missing",
                "error": "Request has no credential for this document",
                "lease": record.to_dict(),
            },
            None,
        )
    if matched.get("lease_id") != record.lease_id:
        return (
            {
                "success": False,
                "error_code": "lease_id_mismatch",
                "error": "Lease identifier does not match the active lease",
                "lease": record.to_dict(),
            },
            None,
        )
    if int(matched.get("generation", 0)) != record.generation:
        return (
            {
                "success": False,
                "error_code": "lease_generation_mismatch",
                "error": "Lease generation has been fenced",
                "lease": record.to_dict(),
            },
            None,
        )
    return None, matched.get("token")


def check_mutation_allowed(
    doc_key: str,
    *,
    identity: dict[str, Any] | None = None,
    allowed_states: set[str] | None = None,
) -> dict[str, Any]:
    """Enforce exact owner, document, generation, and token authorization."""
    identity = dict(identity or get_request_identity())
    instance_id = identity.get("instance_id")
    record = _load_mutation_record(doc_key)
    if record is None:
        return {
            "success": False,
            "error_code": "document_not_locked",
            "error": (
                "No document lock held for this document. Call acquire_document_lock "
                "with an explicit document identity before mutating."
            ),
        }
    permitted = allowed_states or {LeaseState.LOCKED_IDLE.value}
    if state_error := _mutation_state_error(record, permitted):
        return state_error
    if owner_error := _mutation_owner_error(record, instance_id):
        return owner_error
    credential_error, token = _mutation_credential_error(record, identity)
    if credential_error is not None:
        return credential_error
    if not token:
        return {
            "success": False,
            "error_code": "missing_lease_token",
            "error": "Every mutation must present the active lease token",
            "lease": record.to_dict(),
        }
    if not hmac.compare_digest(str(token), str(record.token)):
        return {
            "success": False,
            "error_code": "invalid_lease_token",
            "error": "Presented lease token does not match the active lease",
            "lease": record.to_dict(),
        }
    return {"success": True, "lease": record.to_dict()}


def check_persisted_mutation_allowed(
    doc_key: str,
    *,
    identity: dict[str, Any] | None = None,
    allowed_states: set[str] | None = None,
) -> dict[str, Any]:
    """Authorize a live v1 record and prove its adjacent sidecar is unchanged."""
    authorization = check_mutation_allowed(
        doc_key,
        identity=identity,
        allowed_states=allowed_states,
    )
    if not authorization.get("success"):
        return authorization
    if not (os.path.isabs(doc_key) and doc_key.lower().endswith(".fcstd")):
        return authorization
    with _registry_lock:
        record = _registry.get(doc_key)
    persisted = _read_sidecar(sidecar_path_for(doc_key))
    if record is None or not persisted:
        return {
            "success": False,
            "error_code": "sidecar_missing",
            "error": "The compatibility sidecar is missing or unreadable",
        }
    if "schema_version" in persisted or "record_kind" in persisted:
        return {
            "success": False,
            "error_code": "sidecar_protocol_mismatch",
            "error": "The sidecar is not a protocol-v1 compatibility record",
        }
    expected_fingerprint = record.to_sidecar_dict()["token_fingerprint"]
    try:
        generation_matches = int(persisted.get("generation", 0)) == int(
            record.generation
        )
    except (TypeError, ValueError):
        generation_matches = False
    if (
        persisted.get("lease_id") != record.lease_id
        or not generation_matches
        or not hmac.compare_digest(
            str(persisted.get("token_fingerprint", "")),
            str(expected_fingerprint),
        )
    ):
        return {
            "success": False,
            "error_code": "sidecar_replaced",
            "error": "The compatibility sidecar no longer matches the live lease",
        }
    return authorization


def annotate_read_result(result: Any, doc_key: str | None) -> Any:
    """Attach lock ownership info to read-only results when another instance owns D."""
    if not doc_key:
        return result
    record = _load_mutation_record(doc_key)
    if record is None:
        return result
    identity = get_request_identity()
    owned_by_other = record.instance_id != identity.get("instance_id")
    annotation = {
        "document_lock": {
            "doc_key": record.doc_key,
            "state": record.state,
            "instance_id": record.instance_id,
            "client": record.client,
            "owned_by_caller": not owned_by_other,
            "owned_by_other": owned_by_other,
        }
    }
    if isinstance(result, dict):
        merged = dict(result)
        merged.update(annotation)
        return merged
    return {"result": result, **annotation}
