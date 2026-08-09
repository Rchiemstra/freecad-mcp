"""Document lease service operations — registry core."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from ..errors.authorization_error import AuthorizationError
from ..errors.coordination_error import CoordinationError
from ..errors.lease_state_error import LeaseStateError
from ..model import (
    DocumentSelector,
    LeaseCredential,
    LeaseRecord,
    LeaseState,
    token_matches,
)
from ..sidecar import (
    SidecarError,
)
from .constants import (
    OWNER_AUTHORIZABLE_STATES,
)


def _validate_credential_shape(credential: LeaseCredential) -> None:
    if not isinstance(credential, LeaseCredential):
        raise AuthorizationError("a complete LeaseCredential is required")
    if (
        not credential.lease_id
        or not credential.document_session_uuid
        or credential.generation < 1
        or not credential.token
        or not credential.mcp_instance_id
    ):
        raise AuthorizationError(
            "lease id, document, generation, token, and authenticated MCP runtime are required"
        )


def _validate_credential_record_match(
    self,
    credential: LeaseCredential,
    record: LeaseRecord,
    *,
    selector: DocumentSelector | Mapping[str, Any] | str | None,
) -> None:
    if selector is not None:
        identity = self.identity_service.resolve(selector)
        if identity.session_uuid != credential.document_session_uuid:
            raise AuthorizationError("credential does not match the selected document")
    if record.lease_id != credential.lease_id:
        raise AuthorizationError("lease id mismatch")
    if record.generation != credential.generation:
        raise AuthorizationError("lease fencing generation mismatch")
    if record.owner.mcp_instance_id != credential.mcp_instance_id:
        raise AuthorizationError("authenticated MCP runtime does not own this lease")
    if not token_matches(credential.token, record.token_fingerprint):
        raise AuthorizationError("lease token mismatch")


def _commit(self, current: LeaseRecord, updated: LeaseRecord) -> LeaseRecord:
    """Persist first, then publish the in-memory successor."""

    session_uuid = current.document.session_uuid
    path = self._sidecar_path(current)
    if path is not None:
        try:
            self.sidecar_store.replace(path, updated, expected=current)
        except SidecarError as exc:
            raise CoordinationError(
                f"unable to persist lease transition: {exc}"
            ) from exc
    self._records[session_uuid] = updated
    return updated


def _record_for_credential(
    self,
    credential: LeaseCredential,
    *,
    allowed_states: Iterable[LeaseState] = OWNER_AUTHORIZABLE_STATES,
    selector: DocumentSelector | Mapping[str, Any] | str | None = None,
) -> LeaseRecord:
    _validate_credential_shape(credential)
    record = self._records.get(credential.document_session_uuid)
    if record is None:
        raise AuthorizationError("no active lease exists for this document")
    _validate_credential_record_match(
        self, credential, record, selector=selector
    )
    allowed = frozenset(allowed_states)
    if record.state not in allowed:
        raise LeaseStateError(
            f"state {record.state.value} forbids this operation",
            details={"state": record.state.value},
        )
    self._assert_sidecar_matches(record)
    return record
