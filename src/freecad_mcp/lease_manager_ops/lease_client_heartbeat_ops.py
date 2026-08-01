"""LeaseClientManager method implementations."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .canonicalize import canonicalize_document_path
from .heartbeat_helpers import heartbeat_item_lease_state, is_timeout_stale_heartbeat_item
from .lease_credential import LeaseCredential
from .lease_not_found_error import LeaseNotFoundError
from .lease_revocation import LeaseRevocation
from .rpc_request_context import RpcRequestContext
from .stale_recovery_constants import _REVOCATION_ERROR_CODES


def apply_heartbeat_response(
        manager,
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
        with manager._lock:
            response_secrets = manager._secret_snapshot_locked()

        revoked: list[LeaseRevocation] = []
        for item in results:
            if not isinstance(item, Mapping):
                continue
            session_uuid = str(
                item.get("document_session_uuid") or item.get("session_uuid") or ""
            )
            if not session_uuid and item.get("lease_id"):
                lease_id = str(item["lease_id"])
                with manager._lock:
                    session_uuid = next(
                        (
                            key
                            for key, credential in manager._credentials.items()
                            if credential.lease_id == lease_id
                        ),
                        "",
                    )
            if not session_uuid:
                continue
            state = heartbeat_item_lease_state(item)
            error_code = str(item.get("error_code") or item.get("code") or "").upper()
            user_intervened = (
                bool(item.get("user_intervened")) or state == "USER_INTERVENED"
            )
            # Timeout-induced STALE retains the exact credential for reconcile.
            if is_timeout_stale_heartbeat_item(item):
                continue
            fenced = (
                bool(item.get("revoked"))
                or user_intervened
                or error_code in _REVOCATION_ERROR_CODES
            )
            if not fenced:
                continue
            reason = manager._redact_text_with_secrets(
                item.get("error")
                or item.get("message")
                or error_code
                or state
                or "lease revoked by addon",
                response_secrets,
            )
            tombstone = manager.revoke(
                session_uuid,
                reason=reason,
                user_intervened=user_intervened,
            )
            if tombstone is not None:
                revoked.append(tombstone)
        return tuple(revoked)


def credentials_snapshot(manager) -> tuple[LeaseCredential, ...]:
        with manager._lock:
            return tuple(manager._credentials[key] for key in sorted(manager._credentials))


def build_request_context(
        manager,
        *,
        document_session_uuids: Iterable[str] = (),
        canonical_paths: Iterable[str | os.PathLike[str]] = (),
        operation_name: str = "",
        task_id: str = "",
        request_id: str | None = None,
    ) -> RpcRequestContext:
        """Resolve selectors once and freeze their credentials for one call."""

        with manager._lock:
            manager._require_connected_locked()
            assert manager._session_token is not None
            credentials: dict[str, LeaseCredential] = {}
            for session_uuid in document_session_uuids:
                credential = manager._credentials.get(session_uuid)
                if credential is None:
                    raise LeaseNotFoundError(
                        f"no active lease credential for {session_uuid!r}"
                    )
                credentials[session_uuid] = credential
            for path in canonical_paths:
                alias = canonicalize_document_path(path)
                session_uuid = manager._alias_to_session.get(alias)
                credential = manager._credentials.get(session_uuid or "")
                if credential is None:
                    raise LeaseNotFoundError(
                        f"no active lease credential for path {os.fspath(path)!r}"
                    )
                credentials[credential.document_session_uuid] = credential
            return RpcRequestContext(
                request_id=request_id or str(uuid.uuid4()),
                session_token=manager._session_token,
                lease_credentials=tuple(
                    credentials[key] for key in sorted(credentials)
                ),
                operation_name=operation_name,
                task_id=task_id,
            )


def build_heartbeat_payload(
        manager,
        current_operations: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Build one batch renewal payload without allowing caller-set states."""

        with manager._lock:
            manager._require_connected_locked()
            return manager._build_heartbeat_payload_locked(current_operations)


def build_heartbeat_request(
        manager,
        current_operations: Mapping[str, str] | None = None,
        *,
        request_id: str | None = None,
    ) -> tuple[dict[str, Any], RpcRequestContext]:
        """Atomically snapshot one batch payload and its authenticated session."""

        with manager._lock:
            manager._require_connected_locked()
            payload = manager._build_heartbeat_payload_locked(current_operations)
            context = RpcRequestContext(
                request_id=request_id or str(uuid.uuid4()),
                session_token=manager._session_token or "",
                operation_name="Automatic lease heartbeat",
            )
            return payload, context


def build_heartbeat_envelope(
        manager,
        current_operations: Mapping[str, str] | None = None,
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        payload, context = manager.build_heartbeat_request(
            current_operations, request_id=request_id
        )
        return context.to_envelope("lease_heartbeat_batch", payload)
