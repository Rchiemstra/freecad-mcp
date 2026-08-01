"""Document lease service operations — acquiring reservation."""

from __future__ import annotations

from ..errors.coordination_error import CoordinationError
from ..errors.foreign_recovery_record import ForeignRecoveryRecord
from ..errors.lease_grant import LeaseGrant
from ..errors.lease_service_error import LeaseServiceError
from ..model import (
    DocumentIdentity,
    LeaseCredential,
    LeaseOwner,
    LeaseRecord,
    LeaseState,
    token_fingerprint,
)
from ..sidecar import (
    SidecarError,
    sidecar_path_for,
)
from .constants import (
    bounded_text,
)


def _remember_acquiring_request(
    self, session_uuid: str, acquisition_request_id: str | None
) -> None:
    request_id = str(acquisition_request_id or "").strip()
    if request_id:
        self._acquiring_request_ids[session_uuid] = request_id
    else:
        self._acquiring_request_ids.pop(session_uuid, None)


def _clear_acquiring_request(self, session_uuid: str) -> None:
    self._acquiring_request_ids.pop(session_uuid, None)


def _may_fence_local_active_acquiring(
    self,
    record: LeaseRecord,
    owner: LeaseOwner,
    *,
    session_uuid: str,
    live_acquisition_request_ids: frozenset[str] | None,
) -> bool:
    """Allow fencing of a same-MCP unreturned ACQUIRING reservation.

    Matching ``mcp_instance_id`` alone is not enough: one MCP process may
    have concurrent acquire/adopt requests. Immediate fencing is allowed
    only when the reservation's recorded acquisition request ID is absent
    from the live inflight set (terminal, abandoned, or never tracked).
    """

    existing_owner = str(record.owner.mcp_instance_id or "")
    requesting_owner = str(owner.mcp_instance_id or "")
    if not existing_owner or existing_owner != requesting_owner:
        return False
    recorded = str(self._acquiring_request_ids.get(session_uuid) or "")
    if not recorded:
        # Legacy/unknown publisher: refuse live ACQUIRING fencing; STALE
        # and USER_INTERVENED shapes remain eligible without this flag.
        return False
    live = live_acquisition_request_ids or frozenset()
    return recorded not in live


def _is_unreturned_reservation(
    record: LeaseRecord,
    *,
    allow_active_acquiring: bool = False,
) -> bool:
    """Recognize a fenced reservation that never reached promotion.

    This narrow shape excludes every lease that could contain agent edits or
    a completed recovery snapshot. A clean acquisition or a freshly confirmed
    dirty adoption may therefore fence it without losing recovery authority.

    Active ``ACQUIRING`` is only treated as unreturned when the caller opts
    in via ``allow_active_acquiring`` after proving ownership/runtime safety
    (same MCP instance with a non-live acquisition request id locally, or
    dead FreeCAD owner for foreign records).
    """

    acquiring = (
        allow_active_acquiring
        and record.state == LeaseState.ACQUIRING
        and not record.user_intervened
        and record.error is None
    )
    stale = (
        record.state == LeaseState.STALE
        and not record.user_intervened
        and record.error is not None
        and record.error.code == "LEASE_STALE"
    )
    intervened = (
        record.state == LeaseState.USER_INTERVENED
        and record.user_intervened
        and record.error is not None
        and record.error.code == "USER_INTERVENED"
    )
    return bool(
        (acquiring or stale or intervened)
        and record.document.canonical_path is not None
        and record.last_mutation_revision in {0, 1}
        and record.last_verified_save_revision == 0
        and record.last_successful_save_at is None
        and record.baseline is None
        and not record.validation_complete
        and record.snapshot_id is None
        and record.migration is None
    )


def _replace_unreturned_reservation(
    self,
    previous: LeaseRecord,
    identity: DocumentIdentity,
    owner: LeaseOwner,
    *,
    task_summary: str,
    document_dirty: bool,
    foreign: ForeignRecoveryRecord | None = None,
    acquisition_request_id: str | None = None,
) -> LeaseGrant:
    """CAS-fence one local/foreign reservation whose credential was not returned."""

    if foreign is not None:
        if foreign.local_document != identity or foreign.persisted != previous:
            raise CoordinationError("the imported foreign recovery authority changed")
        path = sidecar_path_for(identity.canonical_path)
        try:
            persisted = self.sidecar_store.read(path)
        except SidecarError as exc:
            raise CoordinationError(
                f"foreign acquisition sidecar is unavailable or invalid: {exc}"
            ) from exc
        if persisted != previous:
            raise CoordinationError(
                "foreign acquisition authority changed after import"
            )
        self._assert_foreign_document_exact(
            identity,
            persisted,
            allow_unreturned_file_replacement=True,
        )
        self._prove_foreign_owner_dead(persisted.owner)

    raw_token = self._token_factory()
    if not raw_token:
        raise LeaseServiceError("token factory returned an empty token")
    generation = (
        max(
            previous.generation,
            self._generations.get(identity.session_uuid, 0),
        )
        + 1
    )
    now = self._utc_clock()
    now_mono = self._monotonic_ns()
    replacement = LeaseRecord(
        lease_id=str(self._uuid_factory()),
        generation=generation,
        token_fingerprint=token_fingerprint(raw_token),
        document=identity,
        owner=owner,
        state=LeaseState.ACQUIRING,
        record_revision=previous.record_revision + 1,
        state_revision=previous.state_revision + 1,
        acquired_at=now,
        last_heartbeat_at=now,
        monotonic_heartbeat_ns=now_mono,
        task_summary=bounded_text(task_summary, 1024),
        dirty=document_dirty,
        last_mutation_revision=1 if document_dirty else 0,
        baseline=None,
        validation_complete=False,
        snapshot_id=None,
    )
    path = self._sidecar_path(previous)
    if path is not None:
        try:
            self.sidecar_store.replace(path, replacement, expected=previous)
        except SidecarError as exc:
            raise CoordinationError(
                f"unreturned acquisition reservation could not be fenced: {exc}"
            ) from exc
    self._records[identity.session_uuid] = replacement
    self._foreign_records.pop(identity.session_uuid, None)
    self._closed_documents.pop(identity.session_uuid, None)
    self._generations[identity.session_uuid] = generation
    self._last_sidecar_heartbeat_ns[identity.session_uuid] = now_mono
    self._remember_acquiring_request(identity.session_uuid, acquisition_request_id)
    credential = LeaseCredential(
        lease_id=replacement.lease_id,
        document_session_uuid=identity.session_uuid,
        generation=generation,
        token=raw_token,
        mcp_instance_id=owner.mcp_instance_id,
    )
    return LeaseGrant(credential=credential, record=replacement)
