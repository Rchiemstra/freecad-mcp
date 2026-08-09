"""Document lease service operations — recover orphaned foreign."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from ..errors.dirty_adoption_error import DirtyAdoptionError
from ..errors.lease_conflict_error import LeaseConflictError
from ..errors.lease_grant import LeaseGrant
from ..model import (
    DocumentSelector,
    LeaseOwner,
    LeaseRecord,
    LiveDocumentValidation,
)
from .cross_layer_handoff import (
    finalize_orphan_cross_layer_grant,
    rollback_foreign_orphan_cross_layer,
)
from .orphan_recovery_ops import (
    commit_orphan_sidecar_create,
    prepare_foreign_orphan_recovery,
)
from .orphan_recovery_validation import validate_orphan_recovery_callbacks


def recover_orphaned_foreign_acquisition(
    self,
    selector: DocumentSelector | Mapping[str, Any] | str,
    owner: LeaseOwner,
    *,
    validation: LiveDocumentValidation,
    snapshot_id: str,
    task_summary: str = "",
    adopt_dirty: bool = False,
    local_confirmation: bool = False,
    authority_handoff: Callable[[LeaseRecord], bool] | None = None,
    authority_rollback: Callable[[], bool] | None = None,
    credential_escrow: Callable[[LeaseGrant], bool] | None = None,
) -> LeaseGrant:
    """Recover cached foreign authority after its sidecar disappeared.

    The caller first snapshots the exact live document under the existing
    core fence. This method then revalidates the cached saved baseline,
    proves the recorded foreign FreeCAD authority inactive, atomically
    creates completed replacement authority, verifies the core handoff,
    and escrows the only raw credential before publishing it in memory.

    Dirty live state is never inferred clean. It requires the normal local
    adoption confirmation and is retained in both the replacement lease and
    recovery snapshot. A sidecar that reappears wins the atomic-create race.
    """

    validate_orphan_recovery_callbacks(
        authority_handoff=authority_handoff,
        authority_rollback=authority_rollback,
        credential_escrow=credential_escrow,
    )
    if adopt_dirty and local_confirmation is not True:
        raise DirtyAdoptionError(
            "dirty-document recovery requires explicit local GUI confirmation"
        )

    identity = self.identity_service.resolve(selector)
    with self._lock:
        foreign = self._foreign_records.get(identity.session_uuid)
        if foreign is None:
            raise LeaseConflictError(
                "the selected document has no foreign recovery record"
            )
        path, _previous, replacement, raw_token, generation, now_mono = (
            prepare_foreign_orphan_recovery(
                self,
                identity,
                foreign,
                owner,
                validation,
                adopt_dirty=adopt_dirty,
                local_confirmation=local_confirmation,
                snapshot_id=snapshot_id,
                task_summary=task_summary,
            )
        )
        sidecar_commit_uncertain = commit_orphan_sidecar_create(
            self, path, replacement
        )

        def rollback(**kwargs: Any) -> None:
            rollback_foreign_orphan_cross_layer(
                self,
                session_uuid=identity.session_uuid,
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
