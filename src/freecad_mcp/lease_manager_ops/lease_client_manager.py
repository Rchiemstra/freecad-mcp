"""Thread-safe MCP-side lease-token owner and document alias index."""

from __future__ import annotations

import os as _os
import threading as _threading
import time as _time
import uuid as _uuid
from collections.abc import Iterable as _Iterable
from collections.abc import Mapping as _Mapping
from collections.abc import Sequence as _Sequence
from datetime import UTC as _UTC
from datetime import datetime as _datetime
from typing import Any as _Any

from .canonicalize import canonicalize_document_path as _canonicalize_document_path
from .heartbeat_helpers import (
    heartbeat_item_lease_state as _heartbeat_item_lease_state,
)
from .heartbeat_helpers import (
    is_timeout_stale_heartbeat_item as _is_timeout_stale_heartbeat_item,
)
from .lease_alias_conflict_error import (
    LeaseAliasConflictError as _LeaseAliasConflictError,
)
from .lease_credential import LeaseCredential as _LeaseCredential
from .lease_manager_closed_error import (
    LeaseManagerClosedError as _LeaseManagerClosedError,
)
from .lease_manager_disconnected_error import (
    LeaseManagerDisconnectedError as _LeaseManagerDisconnectedError,
)
from .lease_manager_error import LeaseManagerError as _LeaseManagerError
from .lease_not_found_error import LeaseNotFoundError as _LeaseNotFoundError
from .lease_revocation import LeaseRevocation as _LeaseRevocation
from .rpc_request_context import RpcRequestContext as _RpcRequestContext
from .stale_recovery_constants import _REVOCATION_ERROR_CODES

__all__ = ("LeaseClientManager", "bind_lease_client_manager")


class LeaseClientManager:
    """Thread-safe MCP-side lease-token owner and document alias index."""

    def __init__(self, *args, **kwargs):
        if args:
            raise TypeError("LeaseClientManager accepts session_token only by keyword")
        unexpected = set(kwargs) - {"session_token"}
        if unexpected:
            raise TypeError(
                "LeaseClientManager got unexpected keyword argument "
                f"{min(unexpected)!r}"
            )
        session_token = kwargs.get("session_token")
        self._lock = _threading.RLock()
        self._credentials: dict[str, _LeaseCredential] = {}
        self._alias_to_session: dict[str, str] = {}
        self._session_aliases: dict[str, set[str]] = {}
        self._revocations: dict[str, _LeaseRevocation] = {}
        self._session_token = session_token
        self._connected = bool(session_token)
        self._closed = False
        self._disconnect_reason = ""
        self._disconnected_at: str | None = None

    def __repr__(self) -> str:
        with self._lock:
            return (
                f"{type(self).__name__}(connected={self._connected!r}, "
                f"closed={self._closed!r}, credential_count={len(self._credentials)!r}, "
                f"revocation_count={len(self._revocations)!r})"
            )

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    def mark_connected(self, session_token: str) -> None:
        if not session_token:
            raise ValueError("session_token must not be empty")
        with self._lock:
            if self._closed:
                raise _LeaseManagerClosedError(
                    "lease manager is closed and cannot accept a new RPC session"
                )
            self._session_token = session_token
            self._connected = True
            self._disconnect_reason = ""
            self._disconnected_at = None

    def close(self, reason: str = "MCP process shutdown") -> None:
        with self._lock:
            self._closed = True
            self._connected = False
            self._disconnect_reason = self._redact_text_with_secrets(
                reason or "MCP process shutdown", self._secret_snapshot_locked()
            )
            self._session_token = None
            self._disconnected_at = _datetime.now(_UTC).isoformat()

    def mark_disconnected(self, reason: str = "connection closed") -> None:
        with self._lock:
            if self._closed:
                return
            self._connected = False
            self._disconnect_reason = self._redact_text_locked(
                reason or "connection closed"
            )
            self._session_token = None
            self._disconnected_at = _datetime.now(_UTC).isoformat()

    def store(
        self,
        credential: _LeaseCredential,
        *,
        canonical_paths: _Iterable[str | _os.PathLike[str]] = (),
        replace: bool = False,
    ) -> _LeaseCredential:
        aliases = {_canonicalize_document_path(path) for path in canonical_paths}
        session_uuid = credential.document_session_uuid
        with self._lock:
            self._require_open_locked()
            current = self._credentials.get(session_uuid)
            if current is not None and current != credential and not replace:
                raise _LeaseManagerError(
                    f"document {session_uuid!r} already has another credential"
                )
            for alias in aliases:
                owner = self._alias_to_session.get(alias)
                if owner is not None and owner != session_uuid:
                    raise _LeaseAliasConflictError(
                        f"document path alias is already assigned to {owner!r}"
                    )
            self._credentials[session_uuid] = credential
            self._session_aliases.setdefault(session_uuid, set()).update(aliases)
            for alias in aliases:
                self._alias_to_session[alias] = session_uuid
            self._revocations.pop(session_uuid, None)
            return credential

    def get(
        self,
        *,
        document_session_uuid: str | None = None,
        canonical_path: str | _os.PathLike[str] | None = None,
    ) -> _LeaseCredential | None:
        path_session: str | None = None
        if canonical_path is not None:
            alias = _canonicalize_document_path(canonical_path)
            with self._lock:
                path_session = self._alias_to_session.get(alias)
        with self._lock:
            if (
                document_session_uuid
                and path_session
                and document_session_uuid != path_session
            ):
                return None
            session_uuid = document_session_uuid or path_session
            return self._credentials.get(session_uuid) if session_uuid else None

    def require(
        self,
        *,
        document_session_uuid: str | None = None,
        canonical_path: str | _os.PathLike[str] | None = None,
    ) -> _LeaseCredential:
        credential = self.get(
            document_session_uuid=document_session_uuid, canonical_path=canonical_path
        )
        if credential is None:
            selector = document_session_uuid or _os.fspath(canonical_path or "")
            raise _LeaseNotFoundError(f"no active lease credential for {selector!r}")
        return credential

    def aliases_for(self, document_session_uuid: str) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._session_aliases.get(document_session_uuid, ())))

    def add_alias(
        self, document_session_uuid: str, canonical_path: str | _os.PathLike[str]
    ) -> str:
        alias = _canonicalize_document_path(canonical_path)
        with self._lock:
            self._require_open_locked()
            if document_session_uuid not in self._credentials:
                raise _LeaseNotFoundError(
                    f"no active lease credential for {document_session_uuid!r}"
                )
            owner = self._alias_to_session.get(alias)
            if owner is not None and owner != document_session_uuid:
                raise _LeaseAliasConflictError(
                    f"document path alias is already assigned to {owner!r}"
                )
            self._alias_to_session[alias] = document_session_uuid
            self._session_aliases.setdefault(document_session_uuid, set()).add(alias)
            return alias

    def migrate_alias(
        self,
        old_path: str | _os.PathLike[str],
        new_path: str | _os.PathLike[str],
        *,
        document_session_uuid: str | None = None,
        retain_old: bool = False,
    ) -> _LeaseCredential:
        old_alias = _canonicalize_document_path(old_path)
        new_alias = _canonicalize_document_path(new_path)
        with self._lock:
            self._require_open_locked()
            old_owner = self._alias_to_session.get(old_alias)
            session_uuid = document_session_uuid or old_owner
            if not session_uuid or old_owner != session_uuid:
                raise _LeaseNotFoundError(
                    "old Save As path is not assigned to the requested document"
                )
            credential = self._credentials.get(session_uuid)
            if credential is None:
                raise _LeaseNotFoundError(
                    f"no active lease credential for {session_uuid!r}"
                )
            new_owner = self._alias_to_session.get(new_alias)
            if new_owner is not None and new_owner != session_uuid:
                raise _LeaseAliasConflictError(
                    f"Save As destination is already assigned to {new_owner!r}"
                )
            self._alias_to_session[new_alias] = session_uuid
            self._session_aliases.setdefault(session_uuid, set()).add(new_alias)
            if not retain_old and old_alias != new_alias:
                self._alias_to_session.pop(old_alias, None)
                self._session_aliases[session_uuid].discard(old_alias)
            return credential

    def revoke(
        self, document_session_uuid: str, *, reason: str, user_intervened: bool = False
    ) -> _LeaseRevocation | None:
        with self._lock:
            credential = self._credentials.get(document_session_uuid)
            if credential is None:
                return self._revocations.get(document_session_uuid)
            safe_reason = self._redact_text_locked(reason or "lease revoked")
            self._credentials.pop(document_session_uuid, None)
            for alias in self._session_aliases.pop(document_session_uuid, set()):
                if self._alias_to_session.get(alias) == document_session_uuid:
                    self._alias_to_session.pop(alias, None)
            revocation = _LeaseRevocation(
                document_session_uuid=document_session_uuid,
                lease_id=credential.lease_id,
                generation=credential.generation,
                reason=safe_reason,
                user_intervened=user_intervened,
            )
            self._revocations[document_session_uuid] = revocation
            return revocation

    def apply_heartbeat_response(
        self, response: _Mapping[str, _Any]
    ) -> tuple[_LeaseRevocation, ...]:
        raw_results: _Any = response.get("leases", response.get("results", ()))
        if isinstance(raw_results, _Mapping):
            results: _Sequence[_Any] = tuple(raw_results.values())
        elif isinstance(raw_results, _Sequence) and not isinstance(
            raw_results, (str, bytes)
        ):
            results = raw_results
        else:
            results = ()
        with self._lock:
            response_secrets = self._secret_snapshot_locked()
        revoked: list[_LeaseRevocation] = []
        for item in results:
            if not isinstance(item, _Mapping):
                continue
            session_uuid = str(
                item.get("document_session_uuid") or item.get("session_uuid") or ""
            )
            if not session_uuid and item.get("lease_id"):
                lease_id = str(item["lease_id"])
                with self._lock:
                    session_uuid = next(
                        (
                            key
                            for key, credential in self._credentials.items()
                            if credential.lease_id == lease_id
                        ),
                        "",
                    )
            if not session_uuid:
                continue
            state = _heartbeat_item_lease_state(item)
            error_code = str(item.get("error_code") or item.get("code") or "").upper()
            user_intervened = (
                bool(item.get("user_intervened")) or state == "USER_INTERVENED"
            )
            if _is_timeout_stale_heartbeat_item(item):
                continue
            fenced = (
                bool(item.get("revoked"))
                or user_intervened
                or error_code in _REVOCATION_ERROR_CODES
            )
            if not fenced:
                continue
            reason = self._redact_text_with_secrets(
                item.get("error")
                or item.get("message")
                or error_code
                or state
                or "lease revoked by addon",
                response_secrets,
            )
            tombstone = self.revoke(
                session_uuid, reason=reason, user_intervened=user_intervened
            )
            if tombstone is not None:
                revoked.append(tombstone)
        return tuple(revoked)

    def credentials_snapshot(self) -> tuple[_LeaseCredential, ...]:
        with self._lock:
            return tuple(self._credentials[key] for key in sorted(self._credentials))

    def build_request_context(
        self,
        *,
        document_session_uuids: _Iterable[str] = (),
        canonical_paths: _Iterable[str | _os.PathLike[str]] = (),
        operation_name: str = "",
        task_id: str = "",
        request_id: str | None = None,
    ) -> _RpcRequestContext:
        with self._lock:
            self._require_connected_locked()
            assert self._session_token is not None
            credentials: dict[str, _LeaseCredential] = {}
            for session_uuid in document_session_uuids:
                credential = self._credentials.get(session_uuid)
                if credential is None:
                    raise _LeaseNotFoundError(
                        f"no active lease credential for {session_uuid!r}"
                    )
                credentials[session_uuid] = credential
            for path in canonical_paths:
                alias = _canonicalize_document_path(path)
                session_uuid = self._alias_to_session.get(alias)
                credential = self._credentials.get(session_uuid or "")
                if credential is None:
                    raise _LeaseNotFoundError(
                        f"no active lease credential for path {_os.fspath(path)!r}"
                    )
                credentials[credential.document_session_uuid] = credential
            return _RpcRequestContext(
                request_id=request_id or str(_uuid.uuid4()),
                session_token=self._session_token,
                lease_credentials=tuple(
                    credentials[key] for key in sorted(credentials)
                ),
                operation_name=operation_name,
                task_id=task_id,
            )

    def build_heartbeat_payload(
        self, current_operations: _Mapping[str, str] | None = None
    ) -> dict[str, _Any]:
        with self._lock:
            self._require_connected_locked()
            return self._build_heartbeat_payload_locked(current_operations)

    def build_heartbeat_request(
        self,
        current_operations: _Mapping[str, str] | None = None,
        *,
        request_id: str | None = None,
    ) -> tuple[dict[str, _Any], _RpcRequestContext]:
        with self._lock:
            self._require_connected_locked()
            payload = self._build_heartbeat_payload_locked(current_operations)
            context = _RpcRequestContext(
                request_id=request_id or str(_uuid.uuid4()),
                session_token=self._session_token or "",
                operation_name="Automatic lease heartbeat",
            )
            return payload, context

    def build_heartbeat_envelope(
        self,
        current_operations: _Mapping[str, str] | None = None,
        *,
        request_id: str | None = None,
    ) -> dict[str, _Any]:
        payload, context = self.build_heartbeat_request(
            current_operations, request_id=request_id
        )
        return context.to_envelope("lease_heartbeat_batch", payload)

    def redacted_status(self) -> dict[str, _Any]:
        with self._lock:
            credentials = []
            for session_uuid in sorted(self._credentials):
                item = self._credentials[session_uuid].redacted()
                item["canonical_paths"] = sorted(
                    self._session_aliases.get(session_uuid, ())
                )
                credentials.append(item)
            return {
                "connected": self._connected,
                "closed": self._closed,
                "disconnect_reason": self._disconnect_reason,
                "disconnected_at": self._disconnected_at,
                "credentials": credentials,
                "revocations": [
                    {
                        "document_session_uuid": item.document_session_uuid,
                        "lease_id": item.lease_id,
                        "generation": item.generation,
                        "reason": item.reason,
                        "user_intervened": item.user_intervened,
                        "revoked_at": item.revoked_at,
                    }
                    for _, item in sorted(self._revocations.items())
                ],
            }

    def _require_connected_locked(self) -> None:
        self._require_open_locked()
        if not self._connected:
            raise _LeaseManagerDisconnectedError(
                self._disconnect_reason or "lease manager is disconnected"
            )
        if not self._session_token:
            raise _LeaseManagerDisconnectedError(
                "no authenticated RPC session is installed"
            )

    def _require_open_locked(self) -> None:
        if self._closed:
            raise _LeaseManagerClosedError("lease manager is closed")

    def _build_heartbeat_payload_locked(
        self, current_operations: _Mapping[str, str] | None
    ) -> dict[str, _Any]:
        operations = current_operations or {}
        leases = []
        for session_uuid in sorted(self._credentials):
            credential = self._credentials[session_uuid]
            item = credential.to_wire()
            operation = operations.get(session_uuid)
            if operation:
                item["current_operation"] = str(operation)
            leases.append(item)
        return {"leases": leases, "client_monotonic_ns": str(_time.monotonic_ns())}

    def redact_text(
        self, value: _Any, *, additional_secrets: _Iterable[str] = ()
    ) -> str:
        with self._lock:
            secrets = (*self._secret_snapshot_locked(), *tuple(additional_secrets))
            return self._redact_text_with_secrets(str(value), secrets)

    def redact_value(
        self, value: _Any, *, additional_secrets: _Iterable[str] = ()
    ) -> _Any:
        with self._lock:
            secrets = (*self._secret_snapshot_locked(), *tuple(additional_secrets))

        def scrub(item: _Any) -> _Any:
            if isinstance(item, str):
                return self._redact_text_with_secrets(item, secrets)
            if isinstance(item, _Mapping):
                return {
                    self._redact_text_with_secrets(str(key), secrets): scrub(child)
                    for key, child in item.items()
                }
            if isinstance(item, tuple):
                return tuple(scrub(child) for child in item)
            if isinstance(item, list):
                return [scrub(child) for child in item]
            return item

        return scrub(value)

    def _secret_snapshot_locked(self) -> tuple[str, ...]:
        secrets = [credential.token for credential in self._credentials.values()]
        if self._session_token:
            secrets.append(self._session_token)
        return tuple(secret for secret in secrets if secret)

    @staticmethod
    def _redact_text_with_secrets(value: _Any, secrets: _Iterable[str]) -> str:
        safe = str(value)
        for secret in secrets:
            if secret:
                safe = safe.replace(secret, "[REDACTED]")
        return safe

    def _redact_text_locked(self, value: str) -> str:
        return self._redact_text_with_secrets(value, self._secret_snapshot_locked())


def bind_lease_client_manager(LeaseClientManager):
    """Retain the old binder call without performing method attachment."""

    del LeaseClientManager


def _compat_init_manager(manager, *, session_token: str | None = None) -> None:
    """Compatibility adapter for the former free initializer."""

    LeaseClientManager.__init__(manager, session_token=session_token)


# Compatibility adapters preserve the old free-function keyword signatures.
# The class above remains the sole owner of every implementation.
def _compat_mark_connected(manager, session_token: str) -> None:
    return LeaseClientManager.mark_connected(manager, session_token)


def _compat_close(manager, reason: str = "MCP process shutdown") -> None:
    return LeaseClientManager.close(manager, reason)


def _compat_mark_disconnected(manager, reason: str = "connection closed") -> None:
    return LeaseClientManager.mark_disconnected(manager, reason)


def _compat_store(
    manager,
    credential: _LeaseCredential,
    *,
    canonical_paths: _Iterable[str | _os.PathLike[str]] = (),
    replace: bool = False,
) -> _LeaseCredential:
    return LeaseClientManager.store(
        manager,
        credential,
        canonical_paths=canonical_paths,
        replace=replace,
    )


def _compat_get(
    manager,
    *,
    document_session_uuid: str | None = None,
    canonical_path: str | _os.PathLike[str] | None = None,
) -> _LeaseCredential | None:
    return LeaseClientManager.get(
        manager,
        document_session_uuid=document_session_uuid,
        canonical_path=canonical_path,
    )


def _compat_require(
    manager,
    *,
    document_session_uuid: str | None = None,
    canonical_path: str | _os.PathLike[str] | None = None,
) -> _LeaseCredential:
    return LeaseClientManager.require(
        manager,
        document_session_uuid=document_session_uuid,
        canonical_path=canonical_path,
    )


def _compat_aliases_for(manager, document_session_uuid: str) -> tuple[str, ...]:
    return LeaseClientManager.aliases_for(manager, document_session_uuid)


def _compat_add_alias(
    manager,
    document_session_uuid: str,
    canonical_path: str | _os.PathLike[str],
) -> str:
    return LeaseClientManager.add_alias(
        manager,
        document_session_uuid,
        canonical_path,
    )


def _compat_migrate_alias(
    manager,
    old_path: str | _os.PathLike[str],
    new_path: str | _os.PathLike[str],
    *,
    document_session_uuid: str | None = None,
    retain_old: bool = False,
) -> _LeaseCredential:
    return LeaseClientManager.migrate_alias(
        manager,
        old_path,
        new_path,
        document_session_uuid=document_session_uuid,
        retain_old=retain_old,
    )


def _compat_revoke(
    manager,
    document_session_uuid: str,
    *,
    reason: str,
    user_intervened: bool = False,
) -> _LeaseRevocation | None:
    return LeaseClientManager.revoke(
        manager,
        document_session_uuid,
        reason=reason,
        user_intervened=user_intervened,
    )


def _compat_apply_heartbeat_response(
    manager,
    response: _Mapping[str, _Any],
) -> tuple[_LeaseRevocation, ...]:
    return LeaseClientManager.apply_heartbeat_response(manager, response)


def _compat_credentials_snapshot(manager) -> tuple[_LeaseCredential, ...]:
    return LeaseClientManager.credentials_snapshot(manager)


def _compat_build_request_context(
    manager,
    *,
    document_session_uuids: _Iterable[str] = (),
    canonical_paths: _Iterable[str | _os.PathLike[str]] = (),
    operation_name: str = "",
    task_id: str = "",
    request_id: str | None = None,
) -> _RpcRequestContext:
    return LeaseClientManager.build_request_context(
        manager,
        document_session_uuids=document_session_uuids,
        canonical_paths=canonical_paths,
        operation_name=operation_name,
        task_id=task_id,
        request_id=request_id,
    )


def _compat_build_heartbeat_payload(
    manager,
    current_operations: _Mapping[str, str] | None = None,
) -> dict[str, _Any]:
    return LeaseClientManager.build_heartbeat_payload(manager, current_operations)


def _compat_build_heartbeat_request(
    manager,
    current_operations: _Mapping[str, str] | None = None,
    *,
    request_id: str | None = None,
) -> tuple[dict[str, _Any], _RpcRequestContext]:
    return LeaseClientManager.build_heartbeat_request(
        manager,
        current_operations,
        request_id=request_id,
    )


def _compat_build_heartbeat_envelope(
    manager,
    current_operations: _Mapping[str, str] | None = None,
    *,
    request_id: str | None = None,
) -> dict[str, _Any]:
    return LeaseClientManager.build_heartbeat_envelope(
        manager,
        current_operations,
        request_id=request_id,
    )


def _compat_redacted_status(manager) -> dict[str, _Any]:
    return LeaseClientManager.redacted_status(manager)


def _compat_require_connected_locked(manager) -> None:
    return LeaseClientManager._require_connected_locked(manager)


def _compat_require_open_locked(manager) -> None:
    return LeaseClientManager._require_open_locked(manager)


def _compat_build_heartbeat_payload_locked(
    manager,
    current_operations: _Mapping[str, str] | None,
) -> dict[str, _Any]:
    return LeaseClientManager._build_heartbeat_payload_locked(
        manager,
        current_operations,
    )


def _compat_redact_text(
    manager,
    value: _Any,
    *,
    additional_secrets: _Iterable[str] = (),
) -> str:
    return LeaseClientManager.redact_text(
        manager,
        value,
        additional_secrets=additional_secrets,
    )


def _compat_redact_value(
    manager,
    value: _Any,
    *,
    additional_secrets: _Iterable[str] = (),
) -> _Any:
    return LeaseClientManager.redact_value(
        manager,
        value,
        additional_secrets=additional_secrets,
    )


def _compat_secret_snapshot_locked(manager) -> tuple[str, ...]:
    return LeaseClientManager._secret_snapshot_locked(manager)


_compat_redact_text_with_secrets = LeaseClientManager._redact_text_with_secrets


def _compat_redact_text_locked(manager, value: str) -> str:
    return LeaseClientManager._redact_text_locked(manager, value)
