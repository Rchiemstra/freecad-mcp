"""LeaseClientManager method implementations."""

from __future__ import annotations

import os
from collections.abc import Iterable
from datetime import UTC, datetime

from .canonicalize import canonicalize_document_path
from .lease_alias_conflict_error import LeaseAliasConflictError
from .lease_credential import LeaseCredential
from .lease_manager_closed_error import LeaseManagerClosedError
from .lease_manager_error import LeaseManagerError
from .lease_not_found_error import LeaseNotFoundError
from .lease_revocation import LeaseRevocation


def mark_connected(manager, session_token: str) -> None:
        """Install a newly authenticated RPC session without altering leases."""

        if not session_token:
            raise ValueError("session_token must not be empty")
        with manager._lock:
            if manager._closed:
                raise LeaseManagerClosedError(
                    "lease manager is closed and cannot accept a new RPC session"
                )
            manager._session_token = session_token
            manager._connected = True
            manager._disconnect_reason = ""
            manager._disconnected_at = None


def close(manager, reason: str = "MCP process shutdown") -> None:
        """Terminally fence new sessions while retaining redacted recovery state."""

        with manager._lock:
            safe_reason = manager._redact_text_with_secrets(
                reason or "MCP process shutdown",
                manager._secret_snapshot_locked(),
            )
            manager._closed = True
            manager._connected = False
            manager._session_token = None
            manager._disconnect_reason = safe_reason
            manager._disconnected_at = datetime.now(UTC).isoformat()


def mark_disconnected(manager, reason: str = "connection closed") -> None:
        """Fence new wire work but retain redacted recovery/lease knowledge.

        Disconnecting is deliberately not equivalent to releasing a lease. The
        addon must decide whether a document is clean, dirty, stale, or in need
        of local recovery.
        """

        with manager._lock:
            if manager._closed:
                return
            manager._connected = False
            safe_reason = manager._redact_text_locked(reason or "connection closed")
            manager._session_token = None
            manager._disconnect_reason = safe_reason
            manager._disconnected_at = datetime.now(UTC).isoformat()


def store(
        manager,
        credential: LeaseCredential,
        *,
        canonical_paths: Iterable[str | os.PathLike[str]] = (),
        replace: bool = False,
    ) -> LeaseCredential:
        """Store a credential and atomically claim its canonical path aliases."""

        aliases = {canonicalize_document_path(path) for path in canonical_paths}
        session_uuid = credential.document_session_uuid
        with manager._lock:
            manager._require_open_locked()
            current = manager._credentials.get(session_uuid)
            if current is not None and current != credential and not replace:
                raise LeaseManagerError(
                    f"document {session_uuid!r} already has another credential"
                )
            for alias in aliases:
                owner = manager._alias_to_session.get(alias)
                if owner is not None and owner != session_uuid:
                    raise LeaseAliasConflictError(
                        f"document path alias is already assigned to {owner!r}"
                    )

            manager._credentials[session_uuid] = credential
            manager._session_aliases.setdefault(session_uuid, set()).update(aliases)
            for alias in aliases:
                manager._alias_to_session[alias] = session_uuid
            manager._revocations.pop(session_uuid, None)
            return credential


def get(
        manager,
        *,
        document_session_uuid: str | None = None,
        canonical_path: str | os.PathLike[str] | None = None,
    ) -> LeaseCredential | None:
        """Look up by stable document UUID and/or path, requiring agreement."""

        path_session: str | None = None
        if canonical_path is not None:
            alias = canonicalize_document_path(canonical_path)
            with manager._lock:
                path_session = manager._alias_to_session.get(alias)
        with manager._lock:
            if (
                document_session_uuid
                and path_session
                and document_session_uuid != path_session
            ):
                return None
            session_uuid = document_session_uuid or path_session
            if not session_uuid:
                return None
            return manager._credentials.get(session_uuid)


def require(
        manager,
        *,
        document_session_uuid: str | None = None,
        canonical_path: str | os.PathLike[str] | None = None,
    ) -> LeaseCredential:
        credential = manager.get(
            document_session_uuid=document_session_uuid,
            canonical_path=canonical_path,
        )
        if credential is None:
            selector = document_session_uuid or os.fspath(canonical_path or "")
            raise LeaseNotFoundError(f"no active lease credential for {selector!r}")
        return credential


def aliases_for(manager, document_session_uuid: str) -> tuple[str, ...]:
        with manager._lock:
            return tuple(sorted(manager._session_aliases.get(document_session_uuid, ())))


def add_alias(
        manager,
        document_session_uuid: str,
        canonical_path: str | os.PathLike[str],
    ) -> str:
        alias = canonicalize_document_path(canonical_path)
        with manager._lock:
            manager._require_open_locked()
            if document_session_uuid not in manager._credentials:
                raise LeaseNotFoundError(
                    f"no active lease credential for {document_session_uuid!r}"
                )
            owner = manager._alias_to_session.get(alias)
            if owner is not None and owner != document_session_uuid:
                raise LeaseAliasConflictError(
                    f"document path alias is already assigned to {owner!r}"
                )
            manager._alias_to_session[alias] = document_session_uuid
            manager._session_aliases.setdefault(document_session_uuid, set()).add(alias)
            return alias


def migrate_alias(
        manager,
        old_path: str | os.PathLike[str],
        new_path: str | os.PathLike[str],
        *,
        document_session_uuid: str | None = None,
        retain_old: bool = False,
    ) -> LeaseCredential:
        """Atomically update the alias index after a verified Save As."""

        old_alias = canonicalize_document_path(old_path)
        new_alias = canonicalize_document_path(new_path)
        with manager._lock:
            manager._require_open_locked()
            old_owner = manager._alias_to_session.get(old_alias)
            session_uuid = document_session_uuid or old_owner
            if not session_uuid or old_owner != session_uuid:
                raise LeaseNotFoundError(
                    "old Save As path is not assigned to the requested document"
                )
            credential = manager._credentials.get(session_uuid)
            if credential is None:
                raise LeaseNotFoundError(
                    f"no active lease credential for {session_uuid!r}"
                )
            new_owner = manager._alias_to_session.get(new_alias)
            if new_owner is not None and new_owner != session_uuid:
                raise LeaseAliasConflictError(
                    f"Save As destination is already assigned to {new_owner!r}"
                )
            manager._alias_to_session[new_alias] = session_uuid
            manager._session_aliases.setdefault(session_uuid, set()).add(new_alias)
            if not retain_old and old_alias != new_alias:
                manager._alias_to_session.pop(old_alias, None)
                manager._session_aliases[session_uuid].discard(old_alias)
            return credential


def revoke(
        manager,
        document_session_uuid: str,
        *,
        reason: str,
        user_intervened: bool = False,
    ) -> LeaseRevocation | None:
        """Discard the secret and all aliases, retaining a redacted tombstone."""

        with manager._lock:
            credential = manager._credentials.get(document_session_uuid)
            if credential is None:
                return manager._revocations.get(document_session_uuid)
            safe_reason = manager._redact_text_locked(reason or "lease revoked")
            manager._credentials.pop(document_session_uuid, None)
            for alias in manager._session_aliases.pop(document_session_uuid, set()):
                if manager._alias_to_session.get(alias) == document_session_uuid:
                    manager._alias_to_session.pop(alias, None)
            revocation = LeaseRevocation(
                document_session_uuid=document_session_uuid,
                lease_id=credential.lease_id,
                generation=credential.generation,
                reason=safe_reason,
                user_intervened=user_intervened,
            )
            manager._revocations[document_session_uuid] = revocation
            return revocation
