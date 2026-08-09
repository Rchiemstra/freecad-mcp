"""MCP-side custody for document lease credentials.

Raw lease tokens deliberately live only in this module's in-memory records and
in the short-lived wire dictionaries produced for authenticated RPC calls.
Public status, reprs, and revocation records are always redacted.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import os
import threading
import time
from typing import Any, Iterable, Mapping, Sequence
import uuid


class LeaseManagerError(RuntimeError):
    """Base error for invalid lease-manager operations."""


class LeaseNotFoundError(LeaseManagerError):
    """Raised when no credential matches a document selector."""


class LeaseAliasConflictError(LeaseManagerError):
    """Raised when a canonical path is already owned by another document."""


class LeaseManagerDisconnectedError(LeaseManagerError):
    """Raised when wire work is requested after the manager disconnected."""


class LeaseManagerClosedError(LeaseManagerDisconnectedError):
    """Raised when work attempts to revive a terminally closed manager."""


def canonicalize_document_path(path: str | os.PathLike[str]) -> str:
    """Return the platform comparison key for a document path.

    ``realpath`` is intentionally used even when the final file does not exist:
    it still resolves the existing parent and gives Save As aliases the same
    normalization rules as an already-saved document.
    """

    value = os.fspath(path).strip()
    if not value:
        raise ValueError("document path must not be empty")
    absolute = os.path.abspath(os.path.normpath(value))
    return os.path.normcase(os.path.realpath(absolute))


@dataclass(frozen=True, slots=True)
class LeaseCredential:
    """Secret credential for exactly one document lease generation."""

    lease_id: str
    document_session_uuid: str
    generation: int
    token: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.lease_id:
            raise ValueError("lease_id must not be empty")
        if not self.document_session_uuid:
            raise ValueError("document_session_uuid must not be empty")
        if not isinstance(self.generation, int) or isinstance(self.generation, bool):
            raise TypeError("generation must be an integer")
        if self.generation < 0:
            raise ValueError("generation must be non-negative")
        if not self.token:
            raise ValueError("token must not be empty")

    @property
    def token_fingerprint(self) -> str:
        """A diagnostic/fencing digest; never a replacement for the token."""

        digest = hashlib.sha256(self.token.encode("utf-8")).hexdigest()
        return f"sha256:{digest}"

    def to_wire(self) -> dict[str, Any]:
        """Serialize for the private authenticated RPC envelope."""

        return {
            "lease_id": self.lease_id,
            "document_session_uuid": self.document_session_uuid,
            "generation": self.generation,
            "token": self.token,
        }

    def redacted(self) -> dict[str, Any]:
        """Serialize for logs/status without any token-derived secret."""

        return {
            "lease_id": self.lease_id,
            "document_session_uuid": self.document_session_uuid,
            "generation": self.generation,
        }


@dataclass(frozen=True, slots=True)
class LeaseRevocation:
    """Non-secret tombstone explaining why a local credential was discarded."""

    document_session_uuid: str
    lease_id: str
    generation: int
    reason: str
    user_intervened: bool = False
    revoked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True, slots=True)
class RpcRequestContext:
    """Immutable authentication context for one v2 RPC invocation."""

    request_id: str
    session_token: str = field(repr=False)
    lease_credentials: tuple[LeaseCredential, ...] = ()
    operation_name: str = ""
    task_id: str = ""
    protocol_version: int = 2

    def __post_init__(self) -> None:
        if self.protocol_version != 2:
            raise ValueError("only RPC protocol version 2 is supported")
        try:
            parsed_request_id = uuid.UUID(str(self.request_id))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("request_id must be a UUID") from exc
        if parsed_request_id.int == 0:
            raise ValueError("request_id must not be the nil UUID")
        object.__setattr__(self, "request_id", str(parsed_request_id))
        if not self.session_token:
            raise ValueError("session_token must not be empty")
        if not isinstance(self.lease_credentials, tuple):
            object.__setattr__(self, "lease_credentials", tuple(self.lease_credentials))
        sessions = [item.document_session_uuid for item in self.lease_credentials]
        if len(sessions) != len(set(sessions)):
            raise ValueError("request context contains duplicate document credentials")

    def to_envelope(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a fresh XML-RPC-serializable envelope for this request."""

        if not method:
            raise ValueError("method must not be empty")
        envelope = {
            "protocol_version": self.protocol_version,
            "request_id": self.request_id,
            "session_token": self.session_token,
            "method": method,
            "params": copy.deepcopy(dict(params or {})),
            "lease_credentials": [item.to_wire() for item in self.lease_credentials],
        }
        if self.operation_name:
            operation = {"name": self.operation_name}
            if self.task_id:
                operation["task_id"] = self.task_id
            envelope["operation"] = operation
        return envelope


_REVOCATION_ERROR_CODES = frozenset(
    {
        "LEASE_REVOKED",
        "USER_INTERVENED",
        "LEASE_GENERATION_MISMATCH",
        "LEASE_TOKEN_MISMATCH",
        "TOKEN_MISMATCH",
    }
)


class LeaseClientManager:
    """Thread-safe MCP-side lease-token owner and document alias index."""

    def __init__(self, *, session_token: str | None = None) -> None:
        self._lock = threading.RLock()
        self._credentials: dict[str, LeaseCredential] = {}
        self._alias_to_session: dict[str, str] = {}
        self._session_aliases: dict[str, set[str]] = {}
        self._revocations: dict[str, LeaseRevocation] = {}
        self._session_token = session_token
        self._connected = bool(session_token)
        self._closed = False
        self._disconnect_reason = ""
        self._disconnected_at: str | None = None

    def __repr__(self) -> str:
        with self._lock:
            return (
                f"{type(self).__name__}(connected={self._connected!r}, "
                f"closed={self._closed!r}, "
                f"credential_count={len(self._credentials)!r}, "
                f"revocation_count={len(self._revocations)!r})"
            )

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    def mark_connected(self, session_token: str) -> None:
        """Install a newly authenticated RPC session without altering leases."""

        if not session_token:
            raise ValueError("session_token must not be empty")
        with self._lock:
            if self._closed:
                raise LeaseManagerClosedError(
                    "lease manager is closed and cannot accept a new RPC session"
                )
            self._session_token = session_token
            self._connected = True
            self._disconnect_reason = ""
            self._disconnected_at = None

    def close(self, reason: str = "MCP process shutdown") -> None:
        """Terminally fence new sessions while retaining redacted recovery state."""

        with self._lock:
            safe_reason = self._redact_text_with_secrets(
                reason or "MCP process shutdown",
                self._secret_snapshot_locked(),
            )
            self._closed = True
            self._connected = False
            self._session_token = None
            self._disconnect_reason = safe_reason
            self._disconnected_at = datetime.now(timezone.utc).isoformat()

    def mark_disconnected(self, reason: str = "connection closed") -> None:
        """Fence new wire work but retain redacted recovery/lease knowledge.

        Disconnecting is deliberately not equivalent to releasing a lease. The
        addon must decide whether a document is clean, dirty, stale, or in need
        of local recovery.
        """

        with self._lock:
            if self._closed:
                return
            self._connected = False
            safe_reason = self._redact_text_locked(reason or "connection closed")
            self._session_token = None
            self._disconnect_reason = safe_reason
            self._disconnected_at = datetime.now(timezone.utc).isoformat()

    def store(
        self,
        credential: LeaseCredential,
        *,
        canonical_paths: Iterable[str | os.PathLike[str]] = (),
        replace: bool = False,
    ) -> LeaseCredential:
        """Store a credential and atomically claim its canonical path aliases."""

        aliases = {canonicalize_document_path(path) for path in canonical_paths}
        session_uuid = credential.document_session_uuid
        with self._lock:
            self._require_open_locked()
            current = self._credentials.get(session_uuid)
            if current is not None and current != credential and not replace:
                raise LeaseManagerError(
                    f"document {session_uuid!r} already has another credential"
                )
            for alias in aliases:
                owner = self._alias_to_session.get(alias)
                if owner is not None and owner != session_uuid:
                    raise LeaseAliasConflictError(
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
        canonical_path: str | os.PathLike[str] | None = None,
    ) -> LeaseCredential | None:
        """Look up by stable document UUID and/or path, requiring agreement."""

        path_session: str | None = None
        if canonical_path is not None:
            alias = canonicalize_document_path(canonical_path)
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
            if not session_uuid:
                return None
            return self._credentials.get(session_uuid)

    def require(
        self,
        *,
        document_session_uuid: str | None = None,
        canonical_path: str | os.PathLike[str] | None = None,
    ) -> LeaseCredential:
        credential = self.get(
            document_session_uuid=document_session_uuid,
            canonical_path=canonical_path,
        )
        if credential is None:
            selector = document_session_uuid or os.fspath(canonical_path or "")
            raise LeaseNotFoundError(f"no active lease credential for {selector!r}")
        return credential

    def aliases_for(self, document_session_uuid: str) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._session_aliases.get(document_session_uuid, ())))

    def add_alias(
        self,
        document_session_uuid: str,
        canonical_path: str | os.PathLike[str],
    ) -> str:
        alias = canonicalize_document_path(canonical_path)
        with self._lock:
            self._require_open_locked()
            if document_session_uuid not in self._credentials:
                raise LeaseNotFoundError(
                    f"no active lease credential for {document_session_uuid!r}"
                )
            owner = self._alias_to_session.get(alias)
            if owner is not None and owner != document_session_uuid:
                raise LeaseAliasConflictError(
                    f"document path alias is already assigned to {owner!r}"
                )
            self._alias_to_session[alias] = document_session_uuid
            self._session_aliases.setdefault(document_session_uuid, set()).add(alias)
            return alias

    def migrate_alias(
        self,
        old_path: str | os.PathLike[str],
        new_path: str | os.PathLike[str],
        *,
        document_session_uuid: str | None = None,
        retain_old: bool = False,
    ) -> LeaseCredential:
        """Atomically update the alias index after a verified Save As."""

        old_alias = canonicalize_document_path(old_path)
        new_alias = canonicalize_document_path(new_path)
        with self._lock:
            self._require_open_locked()
            old_owner = self._alias_to_session.get(old_alias)
            session_uuid = document_session_uuid or old_owner
            if not session_uuid or old_owner != session_uuid:
                raise LeaseNotFoundError(
                    "old Save As path is not assigned to the requested document"
                )
            credential = self._credentials.get(session_uuid)
            if credential is None:
                raise LeaseNotFoundError(
                    f"no active lease credential for {session_uuid!r}"
                )
            new_owner = self._alias_to_session.get(new_alias)
            if new_owner is not None and new_owner != session_uuid:
                raise LeaseAliasConflictError(
                    f"Save As destination is already assigned to {new_owner!r}"
                )
            self._alias_to_session[new_alias] = session_uuid
            self._session_aliases.setdefault(session_uuid, set()).add(new_alias)
            if not retain_old and old_alias != new_alias:
                self._alias_to_session.pop(old_alias, None)
                self._session_aliases[session_uuid].discard(old_alias)
            return credential

    def revoke(
        self,
        document_session_uuid: str,
        *,
        reason: str,
        user_intervened: bool = False,
    ) -> LeaseRevocation | None:
        """Discard the secret and all aliases, retaining a redacted tombstone."""

        with self._lock:
            credential = self._credentials.get(document_session_uuid)
            if credential is None:
                return self._revocations.get(document_session_uuid)
            safe_reason = self._redact_text_locked(reason or "lease revoked")
            self._credentials.pop(document_session_uuid, None)
            for alias in self._session_aliases.pop(document_session_uuid, set()):
                if self._alias_to_session.get(alias) == document_session_uuid:
                    self._alias_to_session.pop(alias, None)
            revocation = LeaseRevocation(
                document_session_uuid=document_session_uuid,
                lease_id=credential.lease_id,
                generation=credential.generation,
                reason=safe_reason,
                user_intervened=user_intervened,
            )
            self._revocations[document_session_uuid] = revocation
            return revocation

    def apply_heartbeat_response(
        self,
        response: Mapping[str, Any],
    ) -> tuple[LeaseRevocation, ...]:
        """Revoke credentials fenced by heartbeat/user-intervention results."""

        raw_results: Any = response.get("leases", response.get("results", ()))
        if isinstance(raw_results, Mapping):
            results: Sequence[Any] = tuple(raw_results.values())
        elif isinstance(raw_results, Sequence) and not isinstance(
            raw_results, (str, bytes)
        ):
            results = raw_results
        else:
            results = ()

        # Snapshot every currently held secret before processing any item. A
        # batch can revoke multiple leases, and later diagnostics must still be
        # scrubbed even after an earlier credential has been discarded.
        with self._lock:
            response_secrets = self._secret_snapshot_locked()

        revoked: list[LeaseRevocation] = []
        for item in results:
            if not isinstance(item, Mapping):
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
            state = str(item.get("state") or "").upper()
            error_code = str(item.get("error_code") or item.get("code") or "").upper()
            user_intervened = (
                bool(item.get("user_intervened")) or state == "USER_INTERVENED"
            )
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
                session_uuid,
                reason=reason,
                user_intervened=user_intervened,
            )
            if tombstone is not None:
                revoked.append(tombstone)
        return tuple(revoked)

    def credentials_snapshot(self) -> tuple[LeaseCredential, ...]:
        with self._lock:
            return tuple(self._credentials[key] for key in sorted(self._credentials))

    def build_request_context(
        self,
        *,
        document_session_uuids: Iterable[str] = (),
        canonical_paths: Iterable[str | os.PathLike[str]] = (),
        operation_name: str = "",
        task_id: str = "",
        request_id: str | None = None,
    ) -> RpcRequestContext:
        """Resolve selectors once and freeze their credentials for one call."""

        with self._lock:
            self._require_connected_locked()
            assert self._session_token is not None
            credentials: dict[str, LeaseCredential] = {}
            for session_uuid in document_session_uuids:
                credential = self._credentials.get(session_uuid)
                if credential is None:
                    raise LeaseNotFoundError(
                        f"no active lease credential for {session_uuid!r}"
                    )
                credentials[session_uuid] = credential
            for path in canonical_paths:
                alias = canonicalize_document_path(path)
                session_uuid = self._alias_to_session.get(alias)
                credential = self._credentials.get(session_uuid or "")
                if credential is None:
                    raise LeaseNotFoundError(
                        f"no active lease credential for path {os.fspath(path)!r}"
                    )
                credentials[credential.document_session_uuid] = credential
            return RpcRequestContext(
                request_id=request_id or str(uuid.uuid4()),
                session_token=self._session_token,
                lease_credentials=tuple(
                    credentials[key] for key in sorted(credentials)
                ),
                operation_name=operation_name,
                task_id=task_id,
            )

    def build_heartbeat_payload(
        self,
        current_operations: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Build one batch renewal payload without allowing caller-set states."""

        with self._lock:
            self._require_connected_locked()
            return self._build_heartbeat_payload_locked(current_operations)

    def build_heartbeat_request(
        self,
        current_operations: Mapping[str, str] | None = None,
        *,
        request_id: str | None = None,
    ) -> tuple[dict[str, Any], RpcRequestContext]:
        """Atomically snapshot one batch payload and its authenticated session."""

        with self._lock:
            self._require_connected_locked()
            payload = self._build_heartbeat_payload_locked(current_operations)
            context = RpcRequestContext(
                request_id=request_id or str(uuid.uuid4()),
                session_token=self._session_token or "",
                operation_name="Automatic lease heartbeat",
            )
            return payload, context

    def build_heartbeat_envelope(
        self,
        current_operations: Mapping[str, str] | None = None,
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        payload, context = self.build_heartbeat_request(
            current_operations, request_id=request_id
        )
        return context.to_envelope("lease_heartbeat_batch", payload)

    def redacted_status(self) -> dict[str, Any]:
        """Return a stable, fully non-secret diagnostic snapshot."""

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
            raise LeaseManagerDisconnectedError(
                self._disconnect_reason or "lease manager is disconnected"
            )
        if not self._session_token:
            raise LeaseManagerDisconnectedError(
                "no authenticated RPC session is installed"
            )

    def _require_open_locked(self) -> None:
        if self._closed:
            raise LeaseManagerClosedError("lease manager is closed")

    def _build_heartbeat_payload_locked(
        self,
        current_operations: Mapping[str, str] | None,
    ) -> dict[str, Any]:
        operations = current_operations or {}
        leases = []
        for session_uuid in sorted(self._credentials):
            credential = self._credentials[session_uuid]
            item = credential.to_wire()
            operation = operations.get(session_uuid)
            if operation:
                item["current_operation"] = str(operation)
            leases.append(item)
        return {
            "leases": leases,
            # XML-RPC's standard ``int`` is limited to signed 32-bit. Keep the
            # nanosecond clock lossless and wire-safe as decimal text.
            "client_monotonic_ns": str(time.monotonic_ns()),
        }

    def redact_text(
        self,
        value: Any,
        *,
        additional_secrets: Iterable[str] = (),
    ) -> str:
        """Scrub every currently held credential from diagnostic text."""

        with self._lock:
            secrets = (*self._secret_snapshot_locked(), *tuple(additional_secrets))
            return self._redact_text_with_secrets(str(value), secrets)

    def redact_value(
        self,
        value: Any,
        *,
        additional_secrets: Iterable[str] = (),
    ) -> Any:
        """Return a recursively scrubbed copy suitable for logs/public errors."""

        with self._lock:
            secrets = (*self._secret_snapshot_locked(), *tuple(additional_secrets))

        def scrub(item: Any) -> Any:
            if isinstance(item, str):
                return self._redact_text_with_secrets(item, secrets)
            if isinstance(item, Mapping):
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
    def _redact_text_with_secrets(value: Any, secrets: Iterable[str]) -> str:
        safe = str(value)
        for secret in secrets:
            if secret:
                safe = safe.replace(secret, "[REDACTED]")
        return safe

    def _redact_text_locked(self, value: str) -> str:
        return self._redact_text_with_secrets(value, self._secret_snapshot_locked())
