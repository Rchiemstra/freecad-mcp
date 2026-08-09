"""Document lease service operations — foreign import."""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from ..errors.coordination_error import CoordinationError
from ..errors.foreign_recovery_error import ForeignRecoveryError
from ..errors.foreign_recovery_record import ForeignRecoveryRecord
from ..errors.lease_conflict_error import LeaseConflictError
from ..model import (
    DocumentIdentity,
    DocumentSelector,
    LeaseErrorInfo,
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

_FOREIGN_TAKEOVER_ELIGIBLE_STATES = frozenset(
    {
        LeaseState.ACQUIRING,
        LeaseState.LOCKED_IDLE,
        LeaseState.LOCKED_EDITING,
        LeaseState.LOCKED_RECOMPUTING,
        LeaseState.LOCKED_SAVING,
        LeaseState.LOCKED_ERROR,
        LeaseState.CANCELLING,
        LeaseState.RELEASING,
        LeaseState.STALE,
    }
)


def _validate_foreign_takeover_inputs(
    *,
    confirmed: bool,
    reason: str,
    live_document: DocumentIdentity,
    registered: DocumentIdentity,
) -> str:
    if confirmed is not True:
        raise ForeignRecoveryError(
            "foreign recovery takeover requires explicit local confirmation"
        )
    clean_reason = bounded_text(reason, 2048)
    if not clean_reason:
        raise ForeignRecoveryError("foreign recovery takeover requires a reason")
    if not isinstance(live_document, DocumentIdentity):
        raise ForeignRecoveryError("fresh live DocumentIdentity evidence is required")
    if live_document != registered:
        raise ForeignRecoveryError(
            "live document evidence does not match the registered open document"
        )
    return clean_reason


def _read_foreign_takeover_persisted(self, registered: DocumentIdentity, foreign):
    if not registered.canonical_path:
        raise ForeignRecoveryError(
            "foreign recovery takeover requires a saved open document"
        )
    path = sidecar_path_for(registered.canonical_path)
    try:
        persisted = self.sidecar_store.read(path)
    except SidecarError as exc:
        raise CoordinationError(
            f"foreign recovery sidecar is unavailable or invalid: {exc}"
        ) from exc
    if persisted != foreign.persisted:
        raise CoordinationError("foreign recovery authority changed after import")
    self._assert_foreign_document_exact(registered, persisted)
    return path, persisted


def _fence_transitioning_foreign_record(
    self,
    *,
    path: str,
    current: LeaseRecord,
    foreign,
    registered,
    clean_reason: str,
) -> LeaseRecord:
    if current.state not in {LeaseState.ACQUIRING, LeaseState.RELEASING}:
        return current
    uncertain = current.transitioned(
        LeaseState.LOCKED_ERROR,
        error=LeaseErrorInfo(
            code="FOREIGN_TAKEOVER_DURING_TRANSITION",
            message=clean_reason,
            at=self._utc_clock(),
        ),
    )
    try:
        self.sidecar_store.replace(path, uncertain, expected=current)
    except SidecarError as exc:
        raise CoordinationError(f"foreign transition could not be fenced: {exc}") from exc
    foreign = replace(foreign, persisted=uncertain)
    self._foreign_records[registered.session_uuid] = foreign
    return uncertain


def import_adjacent_foreign_recovery(
    self,
    selector: DocumentSelector | Mapping[str, Any] | str,
    *,
    live_document: DocumentIdentity,
) -> dict[str, Any]:
    """Import one strict v2 sidecar without changing its persisted authority.

    The returned/public record is redacted. Malformed, unknown-schema,
    missing, and mismatched-path records are never added to the foreign
    registry and are never rewritten or removed. A replaced filesystem
    identity is accepted only for an explicit ``UNLOCKED_DIRTY`` local
    acknowledgement; acquisition must still prove its owner dead and
    independently validate the newly saved file before CAS fencing it.
    """

    registered = self.identity_service.resolve(selector)
    if not isinstance(live_document, DocumentIdentity):
        raise ForeignRecoveryError("fresh live DocumentIdentity evidence is required")
    if live_document != registered:
        raise ForeignRecoveryError(
            "live document evidence does not match the registered open document"
        )
    if not registered.canonical_path:
        raise ForeignRecoveryError(
            "an unsaved document cannot have an adjacent recovery sidecar"
        )
    path = sidecar_path_for(registered.canonical_path)
    with self._lock:
        if registered.session_uuid in self._records:
            raise LeaseConflictError(
                "the open document already has a local lease record"
            )
        try:
            persisted = self.sidecar_store.read(path)
        except SidecarError as exc:
            raise ForeignRecoveryError(
                f"adjacent sidecar is unavailable or invalid: {exc}"
            ) from exc
        self._assert_foreign_document_exact(
            registered,
            persisted,
            allow_unreturned_file_replacement=True,
            allow_saved_dirty_file_replacement=True,
        )
        existing = self._foreign_records.get(registered.session_uuid)
        if existing is not None:
            if existing.local_document != registered or existing.persisted != persisted:
                raise CoordinationError(
                    "the imported foreign recovery authority changed"
                )
            return existing.to_public_dict()
        imported = ForeignRecoveryRecord(
            local_document=registered,
            persisted=persisted,
            imported_at=self._utc_clock(),
        )
        self._foreign_records[registered.session_uuid] = imported
        self._generations[registered.session_uuid] = max(
            self._generations.get(registered.session_uuid, 0),
            persisted.generation,
        )
        return imported.to_public_dict()


def confirmed_takeover_foreign_recovery(
    self,
    selector: DocumentSelector | Mapping[str, Any] | str,
    *,
    live_document: DocumentIdentity,
    confirmed: bool,
    document_dirty: bool,
    reason: str,
) -> LeaseRecord:
    """Fence a proven-dead same-host owner and bind the local document UUID."""

    registered = self.identity_service.resolve(selector)
    clean_reason = _validate_foreign_takeover_inputs(
        confirmed=confirmed,
        reason=reason,
        live_document=live_document,
        registered=registered,
    )

    with self._lock:
        if registered.session_uuid in self._records:
            raise LeaseConflictError(
                "the open document already has a local lease record"
            )
        foreign = self._foreign_records.get(registered.session_uuid)
        if foreign is None:
            raise LeaseConflictError(
                "the open document has no imported foreign recovery record"
            )
        if foreign.local_document != registered:
            raise ForeignRecoveryError(
                "the open document identity changed after foreign import"
            )
        path, persisted = _read_foreign_takeover_persisted(self, registered, foreign)
        death_proof = self._prove_foreign_owner_dead(persisted.owner)
        if persisted.state not in _FOREIGN_TAKEOVER_ELIGIBLE_STATES:
            raise ForeignRecoveryError(
                f"state {persisted.state.value} requires a different local recovery"
            )

        current = _fence_transitioning_foreign_record(
            self,
            path=path,
            current=persisted,
            foreign=foreign,
            registered=registered,
            clean_reason=clean_reason,
        )

        raw_replacement = self._token_factory()
        if not raw_replacement:
            raise ForeignRecoveryError("token factory returned an empty fencing secret")
        replacement_fingerprint = token_fingerprint(raw_replacement)
        if secrets.compare_digest(replacement_fingerprint, current.token_fingerprint):
            raise ForeignRecoveryError(
                "token factory did not rotate the fencing digest"
            )
        generation = (
            max(
                current.generation,
                self._generations.get(registered.session_uuid, 0),
            )
            + 1
        )
        taken = current.transitioned(
            LeaseState.USER_INTERVENED,
            document=registered,
            generation=generation,
            token_fingerprint=replacement_fingerprint,
            current_operation="",
            user_intervened=True,
            dirty=bool(document_dirty),
            error=LeaseErrorInfo(
                code="USER_INTERVENED",
                message=bounded_text(f"{clean_reason} ({death_proof})", 2048),
                at=self._utc_clock(),
            ),
        )
        try:
            self.sidecar_store.replace(path, taken, expected=current)
        except SidecarError as exc:
            raise CoordinationError(f"foreign takeover CAS failed: {exc}") from exc
        self._records[registered.session_uuid] = taken
        self._foreign_records.pop(registered.session_uuid, None)
        self._generations[registered.session_uuid] = generation
        self._last_sidecar_heartbeat_ns.pop(registered.session_uuid, None)
        return taken
