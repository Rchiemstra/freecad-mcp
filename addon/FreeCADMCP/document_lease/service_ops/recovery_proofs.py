"""Document lease service operations — recovery proofs."""

from __future__ import annotations

from datetime import datetime

from ..errors.foreign_recovery_error import ForeignRecoveryError
from ..errors.foreign_recovery_record import ForeignRecoveryRecord
from ..model import (
    LeaseOwner,
    LeaseRecord,
    LeaseState,
)
from .recovery_proof_checks import (
    assert_same_host_boot_identity,
    foreign_death_process_probe_proof,
    foreign_death_same_process_proof,
    mcp_death_process_probe_proof,
    validate_local_mcp_runtime_match,
    validate_local_runtime_for_foreign_proof,
)


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else None


def _prove_foreign_owner_dead(self, owner: LeaseOwner) -> str:
    """Return bounded proof text, or fail closed when death is uncertain."""

    local, local_started = validate_local_runtime_for_foreign_proof(self)
    owner_started = self._parse_timestamp(owner.freecad_process_started_at)
    if owner_started is None:
        raise ForeignRecoveryError("FreeCAD process-start identity evidence is invalid")
    assert_same_host_boot_identity(local, owner)
    same_process_proof = foreign_death_same_process_proof(
        local,
        owner,
        local_started=local_started,
        owner_started=owner_started,
    )
    if same_process_proof is not None:
        return same_process_proof
    return foreign_death_process_probe_proof(
        self,
        owner,
        owner_started=owner_started,
    )


def _prove_local_mcp_owner_dead(self, owner: LeaseOwner) -> str:
    """Prove that a lease in this addon runtime lost its MCP process.

    The addon/FreeCAD process is intentionally *not* the lease owner. Its
    continued liveness cannot keep authority renewable after the private
    credential-owning MCP process exits. Proof is fail-closed and uses the
    recorded PID together with process-start identity to avoid confusing a
    reused PID with the original owner.
    """

    validate_local_mcp_runtime_match(self, owner)
    return mcp_death_process_probe_proof(self, owner)


def _prove_local_mcp_recovery_authority_inactive(
    self,
    record: LeaseRecord,
) -> str:
    """Prove that the prior credential cannot race a guarded recovery."""

    if self._is_misattributed_worker_snapshot_intervention(record):
        return (
            "previous credential was irrevocably fenced after a "
            "misattributed worker snapshot"
        )
    return self._prove_local_mcp_owner_dead(record.owner)


def _is_misattributed_worker_snapshot_intervention(
    record: LeaseRecord,
) -> bool:
    """Recognize the pre-fix worker ``saveCopy`` observer signature."""

    if (
        record.state != LeaseState.USER_INTERVENED
        or not record.user_intervened
        or record.error is None
        or record.error.code != "USER_INTERVENED"
    ):
        return False
    message = str(record.error.message or "").replace("\\", "/").casefold()
    prefix = "unscoped freecad save detected:"
    if not message.startswith(prefix):
        return False
    target = message[len(prefix) :].strip()
    filename = target.rsplit("/", 1)[-1]
    sequence, separator, remainder = filename.partition("_")
    return bool(
        "freecad_mcp_workers/" in target
        and "/snapshots/" in target
        and separator
        and len(sequence) == 4
        and sequence.isdigit()
        and remainder.endswith(".fcstd")
    )


def _prove_orphaned_foreign_authority_inactive(
    self, foreign: ForeignRecoveryRecord
) -> str:
    """Prove no credential can still drive the imported authority.

    Most records use the normal same-host process/runtime death proof. A
    missing sidecar can also strand a record created by this exact addon
    runtime after its original document session was replaced. In that
    case, the old session's absence from both identity and lease registries
    is stronger authorization evidence than a PID probe: credentials for
    that UUID cannot pass this service's registry fence.
    """

    try:
        return self._prove_foreign_owner_dead(foreign.persisted.owner)
    except ForeignRecoveryError as original_error:
        local = self._local_runtime_identity
        owner = foreign.persisted.owner
        same_runtime = bool(
            local is not None
            and local.addon_profile_id == owner.addon_profile_id
            and local.addon_runtime_id == owner.addon_runtime_id
            and local.freecad_pid == owner.freecad_pid
            and local.freecad_process_started_at == owner.freecad_process_started_at
            and local.boot_id == owner.boot_id
            and local.hostname
            and owner.hostname
            and local.hostname.casefold() == owner.hostname.casefold()
        )
        foreign_session = foreign.persisted.document.session_uuid
        local_session = foreign.local_document.session_uuid
        if not same_runtime or foreign_session == local_session:
            raise original_error
        if (
            foreign_session in self._records
            or foreign_session in self._pending_save_as
            or foreign_session in self._foreign_records
        ):
            raise original_error
        try:
            self.identity_service.resolve(foreign_session)
        except Exception:
            return (
                "recorded document session is no longer registered in the "
                "current addon runtime"
            )
        raise original_error
