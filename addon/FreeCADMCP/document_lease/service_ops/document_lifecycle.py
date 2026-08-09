"""Document lease service operations — document lifecycle."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..errors.coordination_error import CoordinationError
from ..errors.foreign_recovery_error import ForeignRecoveryError
from ..errors.lease_conflict_error import LeaseConflictError
from ..errors.lease_state_error import LeaseStateError
from ..errors.local_recovery_error import LocalRecoveryError
from ..identity import (
    canonicalize_path,
    file_identity_for_path,
)
from ..model import (
    DocumentIdentity,
    DocumentSelector,
    LeaseRecord,
    LeaseState,
)
from ..sidecar import (
    SidecarError,
    sidecar_path_for,
)


def _rebind_authoritative_identity(
    self,
    identity,
    *,
    record: LeaseRecord | None,
    foreign,
) -> DocumentIdentity:
    if record is not None:
        if record.state not in {
            LeaseState.USER_INTERVENED,
            LeaseState.UNLOCKED_DIRTY,
        }:
            raise LeaseStateError(
                "closed-document rebind requires local recovery authority",
                details={"state": record.state.value},
            )
        self._assert_sidecar_matches(record)
        return record.document
    if foreign is None:
        raise LeaseConflictError(
            "the closed document has no retained recovery authority"
        )
    if not identity.canonical_path:
        raise ForeignRecoveryError("foreign recovery document has no saved path")
    try:
        persisted = self.sidecar_store.read(sidecar_path_for(identity.canonical_path))
    except SidecarError as exc:
        raise CoordinationError(
            f"foreign recovery sidecar is unavailable or invalid: {exc}"
        ) from exc
    if persisted != foreign.persisted:
        raise CoordinationError(
            "foreign recovery authority changed after document close"
        )
    return foreign.local_document


def _assert_rebind_identity_match(
    *,
    closed_identity: DocumentIdentity,
    authoritative: DocumentIdentity,
    name: str,
    comparison: str,
    observed_file,
) -> None:
    if (
        closed_identity != authoritative
        or name != authoritative.name
        or comparison != authoritative.comparison_key
        or observed_file != authoritative.file_identity
    ):
        raise CoordinationError(
            "reopened document does not match the closed file identity"
        )


def handle_document_closed(
    self,
    selector: DocumentSelector | Mapping[str, Any] | str,
    *,
    document: Any,
) -> LeaseRecord | dict[str, Any] | None:
    """Retain recovery authority or unregister an unlocked closed proxy."""

    identity = self.identity_service.resolve(selector)
    with self._lock:
        exact = self.identity_service.inspect_registered_document(
            identity.session_uuid,
            document,
        )
        record = self._records.get(identity.session_uuid)
        if record is not None:
            if record.state not in {
                LeaseState.USER_INTERVENED,
                LeaseState.UNLOCKED_DIRTY,
            }:
                raise LeaseStateError(
                    "document close can be marked only after local fencing",
                    details={"state": record.state.value},
                )
            self._assert_sidecar_matches(record)
            if exact != record.document:
                raise CoordinationError(
                    "closed live proxy does not match lease authority"
                )
            self._closed_documents[identity.session_uuid] = (
                id(document),
                exact,
            )
            return record

        foreign = self._foreign_records.get(identity.session_uuid)
        if foreign is not None:
            if exact != foreign.local_document:
                raise CoordinationError(
                    "closed live proxy does not match foreign recovery authority"
                )
            if not exact.canonical_path:
                raise ForeignRecoveryError(
                    "foreign recovery document has no saved path"
                )
            try:
                persisted = self.sidecar_store.read(
                    sidecar_path_for(exact.canonical_path)
                )
            except SidecarError as exc:
                raise CoordinationError(
                    f"foreign recovery sidecar is unavailable or invalid: {exc}"
                ) from exc
            if persisted != foreign.persisted:
                raise CoordinationError(
                    "foreign recovery authority changed before document close"
                )
            self._closed_documents[identity.session_uuid] = (
                id(document),
                exact,
            )
            return foreign.to_public_dict()

        if identity.session_uuid in self._pending_save_as:
            raise CoordinationError(
                "a pending Save As authority cannot be unregistered"
            )
        self._closed_documents.pop(identity.session_uuid, None)
        self.identity_service.unregister(identity.session_uuid)
        return None


def rebind_closed_recovery_document(
    self,
    *,
    document: Any,
) -> DocumentIdentity:
    """Rebind a same-file proxy after an observed recovery-document reopen."""

    name = str(getattr(document, "Name", "") or "").strip()
    raw_path = str(getattr(document, "FileName", "") or "").strip()
    if not name or not raw_path:
        raise LocalRecoveryError(
            "closed-document recovery requires a saved named document"
        )
    canonical, comparison = canonicalize_path(
        raw_path,
        platform=self.identity_service.platform,
    )
    observed_file = file_identity_for_path(
        canonical,
        platform=self.identity_service.platform,
    )
    identity = self.identity_service.resolve(
        {
            "document_name": name,
            "canonical_path": canonical,
        }
    )
    with self._lock:
        closed = self._closed_documents.get(identity.session_uuid)
        if closed is None:
            raise LocalRecoveryError(
                "the previous live document was not observed closing"
            )
        previous_proxy_id, closed_identity = closed
        if id(document) == previous_proxy_id:
            raise LocalRecoveryError(
                "closed-document recovery requires a replacement proxy"
            )
        record = self._records.get(identity.session_uuid)
        foreign = self._foreign_records.get(identity.session_uuid)
        authoritative = _rebind_authoritative_identity(
            self,
            identity,
            record=record,
            foreign=foreign,
        )
        _assert_rebind_identity_match(
            closed_identity=closed_identity,
            authoritative=authoritative,
            name=name,
            comparison=comparison,
            observed_file=observed_file,
        )
        rebound = self.identity_service.rebind_document(
            identity.session_uuid,
            document,
        )
        if rebound != authoritative:
            raise CoordinationError("reopened document rebind changed lease identity")
        self._closed_documents.pop(identity.session_uuid, None)
        return rebound
