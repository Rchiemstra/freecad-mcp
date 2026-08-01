"""Runtime-bound bearer session manager for authenticated RPC v2."""

from __future__ import annotations

import hmac
import secrets
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from ..lease_protocol import sign_handshake_response, verify_handshake_request
from ._session_record import _SessionRecord
from .constants import (
    DEFAULT_SESSION_TTL_SECONDS,
    HANDSHAKE_RESPONSE_KIND,
    MAX_HANDSHAKE_NONCES,
    MAX_SESSION_TTL_SECONDS,
    PROTOCOL_VERSION,
)
from .lease_protocol_error import LeaseProtocolError
from .request_envelope import RequestEnvelope
from .runtime_manifest import RuntimeManifest
from .session_context import SessionContext
from .validation import (
    _format_utc,
    _require_string,
    _require_uuid,
    _token_digest,
    _validate_secret,
    _validate_token,
)


class SessionManager:
    """Issue, validate, expire, and revoke runtime-bound bearer sessions."""

    def __init__(
        self,
        *,
        manifest: RuntimeManifest,
        secret: bytes,
        session_ttl_seconds: float = DEFAULT_SESSION_TTL_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
        utcnow: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not 1 <= session_ttl_seconds <= MAX_SESSION_TTL_SECONDS:
            raise LeaseProtocolError(
                "INVALID_SESSION_TTL", "Session lifetime is outside the supported range"
            )
        self.manifest = manifest
        self._secret = _validate_secret(secret)
        self._session_ttl = float(session_ttl_seconds)
        self._monotonic = monotonic
        self._utcnow = utcnow
        self._sessions_by_digest: dict[str, _SessionRecord] = {}
        self._sessions_by_id: dict[str, _SessionRecord] = {}
        # A signed request nonce is single-use for the complete addon runtime,
        # not merely for one session TTL.  Otherwise a captured handshake could
        # resurrect a dead MCP runtime after the original session expires.
        self._seen_nonces: set[tuple[str, str]] = set()
        self._lock = threading.RLock()

    def perform_handshake(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        verified = verify_handshake_request(
            payload, secret=self._secret, manifest=self.manifest
        )
        now_mono = self._monotonic()
        with self._lock:
            self._prune_locked(now_mono)
            nonce_key = (verified.mcp.runtime_id, verified.client_nonce)
            if nonce_key in self._seen_nonces:
                raise LeaseProtocolError(
                    "HANDSHAKE_REPLAY", "Handshake nonce has already been used"
                )
            if len(self._seen_nonces) >= MAX_HANDSHAKE_NONCES:
                raise LeaseProtocolError(
                    "HANDSHAKE_REPLAY_CACHE_FULL",
                    "Handshake nonce capacity is exhausted for this FreeCAD runtime",
                )
            self._seen_nonces.add(nonce_key)

            token = secrets.token_urlsafe(32)
            session_id = str(uuid.uuid4())
            issued_dt = self._utcnow()
            if issued_dt.tzinfo is None:
                raise LeaseProtocolError(
                    "INVALID_TIMESTAMP", "Session clock must include a timezone"
                )
            issued_dt = issued_dt.astimezone(UTC)
            expires_dt = issued_dt + timedelta(seconds=self._session_ttl)
            negotiated = tuple(
                sorted(set(verified.requested_features).intersection(self.manifest.features))
            )
            context = SessionContext(
                session_id=session_id,
                mcp=verified.mcp,
                negotiated_features=negotiated,
                issued_at=_format_utc(issued_dt),
                expires_at=_format_utc(expires_dt),
            )
            record = _SessionRecord(
                context=context,
                token_digest=_token_digest(token),
                expires_monotonic=now_mono + self._session_ttl,
            )
            self._sessions_by_digest[record.token_digest] = record
            self._sessions_by_id[session_id] = record

        response = {
            "kind": HANDSHAKE_RESPONSE_KIND,
            "protocol_version": PROTOCOL_VERSION,
            "client_nonce": verified.client_nonce,
            "server_nonce": secrets.token_urlsafe(32),
            "session_id": session_id,
            "session_token": token,
            "session_expires_at": context.expires_at,
            "manifest": self.manifest.to_dict(),
            "negotiated_features": list(negotiated),
        }
        return sign_handshake_response(response, self._secret)

    def authenticate(self, session_token: str, *, mcp_runtime_id: str) -> SessionContext:
        token = _validate_token(session_token, "session_token")
        runtime_id = _require_uuid(mcp_runtime_id, "mcp_runtime_id")
        digest = _token_digest(token)
        now_mono = self._monotonic()
        with self._lock:
            record = self._sessions_by_digest.get(digest)
            if record is None or not hmac.compare_digest(record.token_digest, digest):
                raise LeaseProtocolError(
                    "INVALID_SESSION", "RPC session is invalid or no longer available"
                )
            if record.revoked:
                raise LeaseProtocolError(
                    "SESSION_REVOKED", "RPC session has been revoked"
                )
            if now_mono >= record.expires_monotonic:
                raise LeaseProtocolError("SESSION_EXPIRED", "RPC session has expired")
            if not hmac.compare_digest(record.context.mcp.runtime_id, runtime_id):
                raise LeaseProtocolError(
                    "SESSION_BINDING_MISMATCH",
                    "RPC session belongs to a different MCP runtime",
                )
            return record.context

    def authenticate_envelope(
        self,
        payload: Mapping[str, Any] | RequestEnvelope,
        *,
        transport_mcp_runtime_id: str | None = None,
    ) -> tuple[SessionContext, RequestEnvelope]:
        envelope = (
            payload if isinstance(payload, RequestEnvelope) else RequestEnvelope.from_dict(payload)
        )
        if (
            transport_mcp_runtime_id is not None
            and envelope.mcp_runtime_id is not None
            and _require_uuid(transport_mcp_runtime_id, "transport_mcp_runtime_id")
            != envelope.mcp_runtime_id
        ):
            raise LeaseProtocolError(
                "SESSION_BINDING_MISMATCH",
                "Transport and request identify different MCP runtimes",
            )
        runtime_id = transport_mcp_runtime_id or envelope.mcp_runtime_id
        if runtime_id is None:
            raise LeaseProtocolError(
                "MISSING_RUNTIME_BINDING",
                "Authenticated requests must identify the MCP runtime",
            )
        context = self.authenticate(
            envelope.session_token, mcp_runtime_id=runtime_id
        )
        return context, envelope

    def revoke(
        self,
        *,
        session_id: str | None = None,
        session_token: str | None = None,
        reason: str = "revoked",
    ) -> bool:
        if (session_id is None) == (session_token is None):
            raise LeaseProtocolError(
                "INVALID_REVOCATION",
                "Exactly one session identifier is required for revocation",
            )
        with self._lock:
            if session_id is not None:
                record = self._sessions_by_id.get(_require_uuid(session_id, "session_id"))
            else:
                token = _validate_token(session_token, "session_token")
                record = self._sessions_by_digest.get(_token_digest(token))
            if record is None:
                return False
            record.revoked = True
            record.revocation_reason = _require_string(reason, "reason", maximum=128)
            return True

    def revoke_mcp_runtime(self, runtime_id: str, *, reason: str = "runtime revoked") -> int:
        normalized = _require_uuid(runtime_id, "mcp_runtime_id")
        count = 0
        with self._lock:
            for record in self._sessions_by_id.values():
                if record.context.mcp.runtime_id == normalized and not record.revoked:
                    record.revoked = True
                    record.revocation_reason = _require_string(reason, "reason", maximum=128)
                    count += 1
        return count

    def prune_expired(self) -> int:
        with self._lock:
            return self._prune_locked(self._monotonic())

    def _prune_locked(self, now_mono: float) -> int:
        expired_ids = [
            session_id
            for session_id, record in self._sessions_by_id.items()
            if now_mono >= record.expires_monotonic
        ]
        for session_id in expired_ids:
            record = self._sessions_by_id.pop(session_id)
            self._sessions_by_digest.pop(record.token_digest, None)
        return len(expired_ids)


SessionManager.__module__ = "rpc_server.lease_protocol"
