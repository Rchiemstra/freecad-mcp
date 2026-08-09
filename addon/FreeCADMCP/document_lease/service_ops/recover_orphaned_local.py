"""Document lease service operations — recover orphaned local."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from ..errors.lease_grant import LeaseGrant
from ..model import (
    DocumentSelector,
    LeaseOwner,
    LeaseRecord,
    LiveDocumentValidation,
)
from .cross_layer_handoff import (
    finalize_orphan_cross_layer_grant,
    rollback_local_orphan_cross_layer,
)
from .orphan_recovery_ops import (
    commit_orphan_sidecar_replace,
    prepare_local_orphan_recovery,
)
from .orphan_recovery_validation import validate_orphan_recovery_callbacks


def recover_orphaned_local_mcp_acquisition(
    self,
    selector: DocumentSelector | Mapping[str, Any] | str,
    owner: LeaseOwner,
    *,
    validation: LiveDocumentValidation,
    snapshot_id: str,
    task_summary: str = "",
    authority_handoff: Callable[[LeaseRecord], bool] | None = None,
    authority_rollback: Callable[[], bool] | None = None,
    credential_escrow: Callable[[LeaseGrant], bool] | None = None,
) -> LeaseGrant:
    """Atomically acquire a clean document with inactive prior authority.

    The live addon is only the authority registry; it is not lease
    liveness. The caller creates a recovery snapshot under the old core
    fence first. Only then may this method rotate directly to completed
    ``LOCKED_IDLE`` authority after the old process is proven dead or its
    credential is already irrevocably revoked, and fresh GUI/file evidence
    proves that no document state would be lost.
    A snapshot failure therefore leaves the old registry and sidecar
    authority unchanged. When a core-authority handoff callback is
    supplied, the replacement is not published in memory and no credential
    is returned until the sidecar CAS, exact core fence, and optional
    private credential escrow all succeed.
    """

    validate_orphan_recovery_callbacks(
        authority_handoff=authority_handoff,
        authority_rollback=authority_rollback,
        credential_escrow=credential_escrow,
    )
    identity = self.identity_service.resolve(selector)
    with self._lock:
        current, replacement, raw_token, generation, now_mono, path = (
            prepare_local_orphan_recovery(
                self,
                identity,
                owner,
                validation,
                snapshot_id=snapshot_id,
                task_summary=task_summary,
            )
        )
        sidecar_commit_uncertain = commit_orphan_sidecar_replace(
            self,
            path,
            replacement,
            current,
            failure_prefix="local orphan",
        )

        def rollback(**kwargs: Any) -> None:
            rollback_local_orphan_cross_layer(
                self,
                session_uuid=identity.session_uuid,
                current=current,
                replacement=replacement,
                path=path,
                authority_rollback=authority_rollback,
                **kwargs,
            )

        return finalize_orphan_cross_layer_grant(
            self,
            replacement=replacement,
            session_uuid=identity.session_uuid,
            generation=generation,
            raw_token=raw_token,
            mcp_instance_id=owner.mcp_instance_id,
            sidecar_commit_uncertain=sidecar_commit_uncertain,
            authority_handoff=authority_handoff,
            authority_rollback=authority_rollback,
            credential_escrow=credential_escrow,
            rollback=rollback,
            now_mono=now_mono,
        )
