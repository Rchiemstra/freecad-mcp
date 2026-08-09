"""Shared cross-layer orphan recovery commit and rollback helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from ..errors.coordination_error import CoordinationError
from ..errors.lease_grant import LeaseGrant
from ..model import LeaseCredential, LeaseRecord
from ..sidecar import SidecarCommitUncertainError


def exact_persisted_record(
    sidecar_store: Any,
    persisted: LeaseRecord | None,
    proposed: LeaseRecord,
) -> bool:
    if persisted is None:
        return False
    include_task_summary = sidecar_store.persist_task_summary
    return persisted.to_sidecar_dict(
        include_task_summary=include_task_summary
    ) == proposed.to_sidecar_dict(include_task_summary=include_task_summary)


def rollback_local_orphan_cross_layer(
    service: Any,
    *,
    failure_label: str,
    failure: Exception | None,
    session_uuid: str,
    current: LeaseRecord,
    replacement: LeaseRecord,
    path: Any,
    authority_rollback: Callable[[], bool] | None,
) -> None:
    sidecar_restored = False
    authority_restored = False
    rollback_commit_uncertain = False
    rollback_messages: list[str] = []
    restored_record = replace(
        current,
        record_revision=replacement.record_revision + 1,
        state_revision=replacement.state_revision + 1,
    )
    try:
        try:
            service.sidecar_store.replace(
                path,
                restored_record,
                expected=replacement,
            )
        except SidecarCommitUncertainError as exc:
            if not exact_persisted_record(
                service.sidecar_store,
                exc.persisted,
                restored_record,
            ):
                raise
            rollback_commit_uncertain = True
        sidecar_restored = True
        service._records[session_uuid] = restored_record
    except Exception as exc:
        rollback_messages.append(f"sidecar rollback failed: {exc}")
    service._generations[session_uuid] = max(
        service._generations.get(session_uuid, 0),
        replacement.generation,
    )
    if authority_rollback is not None:
        try:
            authority_restored = bool(authority_rollback())
        except Exception as exc:
            authority_restored = False
            rollback_messages.append(f"core authority rollback raised: {exc}")
        if not authority_restored and not any(
            message.startswith("core authority rollback")
            for message in rollback_messages
        ):
            rollback_messages.append("core authority rollback could not be verified")
    detail = (
        "; ".join(rollback_messages)
        if rollback_messages
        else "prior sidecar and core authority were restored"
    )
    error = CoordinationError(
        failure_label + "; " + detail,
        details={
            "failure_stage": failure_label,
            "sidecar_restored": sidecar_restored,
            "core_authority_restored": authority_restored,
            "retain_snapshot": not (sidecar_restored and authority_restored)
            or rollback_commit_uncertain,
        },
    )
    if failure is not None:
        raise error from failure
    raise error


def rollback_foreign_orphan_cross_layer(
    service: Any,
    *,
    failure_label: str,
    failure: Exception | None,
    session_uuid: str,
    replacement: LeaseRecord,
    path: Any,
    authority_rollback: Callable[[], bool] | None,
) -> None:
    sidecar_restored = False
    authority_restored = False
    rollback_commit_uncertain = False
    rollback_messages: list[str] = []
    try:
        try:
            service.sidecar_store.delete(path, expected=replacement)
        except SidecarCommitUncertainError as exc:
            if exc.absent is not True:
                raise
            rollback_commit_uncertain = True
        sidecar_restored = True
    except Exception as exc:
        rollback_messages.append(f"sidecar rollback failed: {exc}")
    service._generations[session_uuid] = max(
        service._generations.get(session_uuid, 0),
        replacement.generation,
    )
    if authority_rollback is not None:
        try:
            authority_restored = bool(authority_rollback())
        except Exception as exc:
            authority_restored = False
            rollback_messages.append(f"core authority rollback raised: {exc}")
        if not authority_restored and not any(
            message.startswith("core authority rollback")
            for message in rollback_messages
        ):
            rollback_messages.append("core authority rollback could not be verified")
    detail = (
        "; ".join(rollback_messages)
        if rollback_messages
        else "missing sidecar and prior core authority were restored"
    )
    error = CoordinationError(
        failure_label + "; " + detail,
        details={
            "failure_stage": failure_label,
            "sidecar_restored": sidecar_restored,
            "core_authority_restored": authority_restored,
            "retain_snapshot": not (sidecar_restored and authority_restored)
            or rollback_commit_uncertain,
        },
    )
    if failure is not None:
        raise error from failure
    raise error


def finalize_orphan_cross_layer_grant(
    service: Any,
    *,
    replacement: LeaseRecord,
    session_uuid: str,
    generation: int,
    raw_token: str,
    mcp_instance_id: str,
    sidecar_commit_uncertain: bool,
    authority_handoff: Callable[[LeaseRecord], bool] | None,
    authority_rollback: Callable[[], bool] | None,
    credential_escrow: Callable[[LeaseGrant], bool] | None,
    rollback: Callable[..., None],
    now_mono: int,
) -> LeaseGrant:
    handoff_error: Exception | None = None
    handoff_complete = True
    if authority_handoff is not None:
        try:
            handoff_complete = bool(authority_handoff(replacement))
        except Exception as exc:
            handoff_error = exc
            handoff_complete = False
    if not handoff_complete:
        rollback(
            failure_label="core mutation authority handoff failed",
            failure=handoff_error,
        )
    credential = LeaseCredential(
        lease_id=replacement.lease_id,
        document_session_uuid=session_uuid,
        generation=generation,
        token=raw_token,
        mcp_instance_id=mcp_instance_id,
    )
    grant = LeaseGrant(
        credential=credential,
        record=replacement,
        coordination_uncertain=sidecar_commit_uncertain,
    )
    escrow_error: Exception | None = None
    escrow_complete = True
    if credential_escrow is not None:
        try:
            escrow_complete = bool(credential_escrow(grant))
        except Exception as exc:
            escrow_error = exc
            escrow_complete = False
    if not escrow_complete:
        rollback(
            failure_label="acquisition credential escrow failed",
            failure=escrow_error,
        )
    service._records[session_uuid] = replacement
    service._foreign_records.pop(session_uuid, None)
    service._closed_documents.pop(session_uuid, None)
    service._generations[session_uuid] = generation
    service._last_sidecar_heartbeat_ns[session_uuid] = now_mono
    service._clear_effective_error_times(session_uuid)
    service._clear_acquiring_request(session_uuid)
    return grant
