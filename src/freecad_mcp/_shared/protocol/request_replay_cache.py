"""Bounded idempotency journal for authenticated RPC v2 requests."""

from __future__ import annotations

import copy as _copy
import hmac as _hmac
import threading as _threading
import time as _time
from collections.abc import Callable as _Callable
from collections.abc import Sequence as _Sequence
from typing import Any as _Any

from ._replay_entry import _ReplayEntry
from .constants import (
    DEFAULT_REPLAY_RESPONSE_MAX_BYTES as _DEFAULT_REPLAY_RESPONSE_MAX_BYTES,
)
from .constants import (
    DEFAULT_REPLAY_TTL_SECONDS as _DEFAULT_REPLAY_TTL_SECONDS,
)
from .protocol_error import ProtocolError as _ProtocolError
from .redaction import redact_sensitive as _redact_sensitive
from .replay_cache_helpers import (
    completion_tombstone as _completion_tombstone,
)
from .replay_cache_helpers import (
    is_completion_tombstone as _is_completion_tombstone,
)
from .replay_cache_helpers import (
    scrub_exact_secrets as _scrub_exact_secrets,
)
from .replay_check import ReplayCheck as _ReplayCheck
from .request_envelope import RequestEnvelope as _RequestEnvelope
from .validation import _require_uuid, canonical_json_bytes

__all__ = ("RequestReplayCache",)


class RequestReplayCache:
    """Bounded process-lifetime idempotency journal for authenticated requests.

    Keys use the authenticated MCP runtime UUID, which remains stable across
    short-lived RPC sessions. Process-pinned entries from uncertain outcomes are
    compacted, never evicted; capacity exhaustion therefore rejects new work fail
    closed.
    """

    def __init__(
        self,
        *,
        ttl_seconds: float = _DEFAULT_REPLAY_TTL_SECONDS,
        max_entries: int = 4096,
        response_max_bytes: int = _DEFAULT_REPLAY_RESPONSE_MAX_BYTES,
        monotonic: _Callable[[], float] = _time.monotonic,
        owner_has_unresolved_lease: _Callable[[str], bool] | None = None,
    ) -> None:
        if ttl_seconds <= 0 or max_entries <= 0 or response_max_bytes <= 0:
            raise ValueError("Replay cache bounds must be positive")
        del owner_has_unresolved_lease
        self._ttl = float(ttl_seconds)
        self._max_entries = int(max_entries)
        self._response_max_bytes = int(response_max_bytes)
        self._monotonic = monotonic
        self._entries: dict[tuple[str, str], _ReplayEntry] = {}
        # Bounded tombstones let request-status distinguish a genuinely
        # unknown UUID from a known result whose retention window elapsed.
        self._expired: dict[tuple[str, str], None] = {}
        self._lock = _threading.RLock()

    def bind_lease_retention_predicate(
        self, predicate: _Callable[[str], bool]
    ) -> None:
        """Deprecated no-op: owner-lease replay pinning was removed at cutover."""

        if not callable(predicate):
            raise TypeError("owner lease predicate must be callable")

    @staticmethod
    def _key(mcp_runtime_id: str, request_id: str) -> tuple[str, str]:
        return (
            _require_uuid(mcp_runtime_id, "mcp_runtime_id"),
            _require_uuid(request_id, "request_id"),
        )

    def claim(
        self,
        mcp_runtime_id: str,
        envelope: _RequestEnvelope,
        *,
        pin_to_owner_leases: bool = False,
    ) -> _ReplayCheck:
        del pin_to_owner_leases
        key = self._key(mcp_runtime_id, envelope.request_id)
        fingerprint = envelope.semantic_fingerprint()
        now = self._monotonic()
        with self._lock:
            self._prune_locked(now)
            existing = self._entries.get(key)
            if existing is not None:
                if not _hmac.compare_digest(existing.fingerprint, fingerprint):
                    raise _ProtocolError(
                        "REQUEST_ID_REUSE",
                        "Request ID was reused with different request content",
                    )
                return _ReplayCheck(
                    existing.state,
                    _copy.deepcopy(existing.response)
                    if existing.state == "completed"
                    else None,
                )
            self._ensure_capacity_locked()
            self._expired.pop(key, None)
            self._entries[key] = _ReplayEntry(
                fingerprint=fingerprint,
                expires_at=now + self._ttl,
            )
            return _ReplayCheck("new")

    def complete(
        self,
        mcp_runtime_id: str,
        envelope: _RequestEnvelope,
        response: _Any,
        *,
        process_pinned: bool = False,
    ) -> None:
        key = self._key(mcp_runtime_id, envelope.request_id)
        fingerprint = envelope.semantic_fingerprint()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or not _hmac.compare_digest(
                entry.fingerprint, fingerprint
            ):
                raise _ProtocolError(
                    "REQUEST_NOT_CLAIMED",
                    "Request must be claimed before its result is cached",
                )
            if entry.late_completion_journaled:
                return
            entry.state = "completed"
            entry.response = self._bounded_response(
                envelope.request_id,
                response,
                secrets=(
                    envelope.session_token,
                    *(item.token for item in envelope.lease_credentials),
                ),
            )
            entry.process_pinned = bool(entry.process_pinned or process_pinned)
            entry.response_compacted = _is_completion_tombstone(entry.response)
            entry.expires_at = self._monotonic() + self._ttl

    def status(self, mcp_runtime_id: str, request_id: str) -> _ReplayCheck:
        """Return request state for the authenticated owning MCP runtime."""

        key = self._key(mcp_runtime_id, request_id)
        now = self._monotonic()
        with self._lock:
            self._prune_locked(now)
            entry = self._entries.get(key)
            if entry is None:
                return _ReplayCheck("expired" if key in self._expired else "unknown")
            return _ReplayCheck(
                entry.state,
                _copy.deepcopy(entry.response) if entry.state == "completed" else None,
            )

    def journal_completion(
        self,
        mcp_runtime_id: str,
        request_id: str,
        response: _Any,
        *,
        secrets: _Sequence[str] = (),
        process_pinned: bool = False,
    ) -> bool:
        """Replace a claimed request result after a late GUI completion.

        The callback is installed only by the authenticated dispatcher that
        already claimed this session/request pair.  It therefore does not need
        to retain a second copy of the (potentially secret-bearing) envelope.
        """

        key = self._key(mcp_runtime_id, request_id)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return False
            entry.state = "completed"
            entry.response = self._bounded_response(
                key[1], response, secrets=tuple(secrets)
            )
            entry.late_completion_journaled = True
            entry.process_pinned = bool(entry.process_pinned or process_pinned)
            entry.response_compacted = _is_completion_tombstone(entry.response)
            entry.expires_at = self._monotonic() + self._ttl
            return True

    def abandon(self, mcp_runtime_id: str, envelope: _RequestEnvelope) -> None:
        """Remove a claim only when its caller proved no side effect began."""

        key = self._key(mcp_runtime_id, envelope.request_id)
        fingerprint = envelope.semantic_fingerprint()
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and _hmac.compare_digest(
                entry.fingerprint, fingerprint
            ):
                self._entries.pop(key, None)

    def prune(self) -> int:
        with self._lock:
            return self._prune_locked(self._monotonic())

    def _prune_locked(self, now: float) -> int:
        removed = 0
        for key, entry in list(self._entries.items()):
            if entry.expires_at > now or entry.state == "in_progress":
                continue
            if entry.process_pinned:
                if not entry.response_compacted:
                    entry.response = _completion_tombstone(key[1])
                    entry.response_compacted = True
                continue
            self._entries.pop(key, None)
            self._remember_expired_locked(key)
            removed += 1
        return removed

    def _remember_expired_locked(self, key: tuple[str, str]) -> None:
        self._expired.pop(key, None)
        self._expired[key] = None
        while len(self._expired) > self._max_entries:
            oldest = next(iter(self._expired))
            self._expired.pop(oldest, None)

    def _ensure_capacity_locked(self) -> None:
        if len(self._entries) < self._max_entries:
            return
        completed = [
            (entry.expires_at, key)
            for key, entry in self._entries.items()
            if entry.state == "completed" and not entry.process_pinned
        ]
        if completed:
            _, oldest_key = min(completed)
            self._entries.pop(oldest_key, None)
            self._remember_expired_locked(oldest_key)
            return
        raise _ProtocolError(
            "REPLAY_JOURNAL_FULL",
            "Authenticated request journal is full while protected entries remain",
        )

    def _bounded_response(
        self, request_id: str, response: _Any, *, secrets: _Sequence[str]
    ) -> _Any:
        safe = _redact_sensitive(_scrub_exact_secrets(response, secrets))
        try:
            encoded = canonical_json_bytes(safe)
        except _ProtocolError:
            return _completion_tombstone(request_id)
        if len(encoded) > self._response_max_bytes:
            return _completion_tombstone(request_id)
        return safe
