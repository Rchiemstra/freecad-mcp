"""Bounded idempotency journal for authenticated RPC v2 requests."""

from __future__ import annotations

import copy
import hmac
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any

from ._replay_entry import _ReplayEntry
from .constants import (
    DEFAULT_REPLAY_RESPONSE_MAX_BYTES,
    DEFAULT_REPLAY_TTL_SECONDS,
)
from .lease_protocol_error import LeaseProtocolError
from .redaction import redact_sensitive
from .replay_cache_helpers import (
    completion_tombstone,
    is_completion_tombstone,
    scrub_exact_secrets,
)
from .replay_check import ReplayCheck
from .request_envelope import RequestEnvelope
from .validation import _require_uuid, canonical_json_bytes


class RequestReplayCache:
    """Bounded process-lifetime idempotency journal for authenticated requests.

    Keys use the authenticated MCP runtime UUID, which remains stable across
    short-lived RPC sessions.  Lease-affecting entries can be pinned while the
    runtime owns unresolved document authority.  Pinned entries are compacted,
    never evicted; capacity exhaustion therefore rejects new work fail closed.
    """

    def __init__(
        self,
        *,
        ttl_seconds: float = DEFAULT_REPLAY_TTL_SECONDS,
        max_entries: int = 4096,
        response_max_bytes: int = DEFAULT_REPLAY_RESPONSE_MAX_BYTES,
        monotonic: Callable[[], float] = time.monotonic,
        owner_has_unresolved_lease: Callable[[str], bool] | None = None,
    ) -> None:
        if ttl_seconds <= 0 or max_entries <= 0 or response_max_bytes <= 0:
            raise ValueError("Replay cache bounds must be positive")
        self._ttl = float(ttl_seconds)
        self._max_entries = int(max_entries)
        self._response_max_bytes = int(response_max_bytes)
        self._monotonic = monotonic
        self._owner_has_unresolved_lease = (
            owner_has_unresolved_lease or (lambda _runtime_id: False)
        )
        self._entries: dict[tuple[str, str], _ReplayEntry] = {}
        # Bounded tombstones let request-status distinguish a genuinely
        # unknown UUID from a known result whose retention window elapsed.
        self._expired: dict[tuple[str, str], None] = {}
        self._lock = threading.RLock()

    def set_owner_lease_predicate(
        self, predicate: Callable[[str], bool]
    ) -> None:
        """Bind the process journal to the current lease authority service."""

        if not callable(predicate):
            raise TypeError("owner lease predicate must be callable")
        with self._lock:
            self._owner_has_unresolved_lease = predicate

    @staticmethod
    def _key(mcp_runtime_id: str, request_id: str) -> tuple[str, str]:
        return (
            _require_uuid(mcp_runtime_id, "mcp_runtime_id"),
            _require_uuid(request_id, "request_id"),
        )

    def claim(
        self,
        mcp_runtime_id: str,
        envelope: RequestEnvelope,
        *,
        pin_to_owner_leases: bool = False,
    ) -> ReplayCheck:
        key = self._key(mcp_runtime_id, envelope.request_id)
        fingerprint = envelope.semantic_fingerprint()
        now = self._monotonic()
        with self._lock:
            self._prune_locked(now)
            existing = self._entries.get(key)
            if existing is not None:
                if not hmac.compare_digest(existing.fingerprint, fingerprint):
                    raise LeaseProtocolError(
                        "REQUEST_ID_REUSE",
                        "Request ID was reused with different request content",
                    )
                return ReplayCheck(
                    existing.state,
                    copy.deepcopy(existing.response)
                    if existing.state == "completed"
                    else None,
                )
            self._ensure_capacity_locked()
            self._expired.pop(key, None)
            self._entries[key] = _ReplayEntry(
                fingerprint=fingerprint,
                expires_at=now + self._ttl,
                pin_to_owner_leases=bool(pin_to_owner_leases),
            )
            return ReplayCheck("new")

    def complete(
        self,
        mcp_runtime_id: str,
        envelope: RequestEnvelope,
        response: Any,
        *,
        process_pinned: bool = False,
    ) -> None:
        key = self._key(mcp_runtime_id, envelope.request_id)
        fingerprint = envelope.semantic_fingerprint()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or not hmac.compare_digest(entry.fingerprint, fingerprint):
                raise LeaseProtocolError(
                    "REQUEST_NOT_CLAIMED",
                    "Request must be claimed before its result is cached",
                )
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
            entry.response_compacted = is_completion_tombstone(entry.response)
            entry.expires_at = self._monotonic() + self._ttl

    def status(self, mcp_runtime_id: str, request_id: str) -> ReplayCheck:
        """Return request state for the authenticated owning MCP runtime."""

        key = self._key(mcp_runtime_id, request_id)
        now = self._monotonic()
        with self._lock:
            self._prune_locked(now)
            entry = self._entries.get(key)
            if entry is None:
                return ReplayCheck(
                    "expired" if key in self._expired else "unknown"
                )
            return ReplayCheck(
                entry.state,
                copy.deepcopy(entry.response)
                if entry.state == "completed"
                else None,
            )

    def journal_completion(
        self,
        mcp_runtime_id: str,
        request_id: str,
        response: Any,
        *,
        secrets: Sequence[str] = (),
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
            entry.process_pinned = bool(entry.process_pinned or process_pinned)
            entry.response_compacted = is_completion_tombstone(entry.response)
            entry.expires_at = self._monotonic() + self._ttl
            return True

    def abandon(self, mcp_runtime_id: str, envelope: RequestEnvelope) -> None:
        """Remove a claim only when its caller proved no side effect began."""

        key = self._key(mcp_runtime_id, envelope.request_id)
        fingerprint = envelope.semantic_fingerprint()
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and hmac.compare_digest(entry.fingerprint, fingerprint):
                self._entries.pop(key, None)

    def prune(self) -> int:
        with self._lock:
            return self._prune_locked(self._monotonic())

    def _prune_locked(self, now: float) -> int:
        removed = 0
        for key, entry in list(self._entries.items()):
            if entry.expires_at > now or entry.state == "in_progress":
                continue
            if self._entry_is_pinned_locked(key, entry):
                if not entry.response_compacted:
                    entry.response = completion_tombstone(key[1])
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

    def _entry_is_pinned_locked(
        self, key: tuple[str, str], entry: _ReplayEntry
    ) -> bool:
        if entry.process_pinned:
            return True
        if not entry.pin_to_owner_leases:
            return False
        try:
            return bool(self._owner_has_unresolved_lease(key[0]))
        except Exception:
            # Losing visibility into lease authority must reduce availability,
            # never permit a duplicate document mutation.
            return True

    def _ensure_capacity_locked(self) -> None:
        if len(self._entries) < self._max_entries:
            return
        completed = [
            (entry.expires_at, key)
            for key, entry in self._entries.items()
            if entry.state == "completed"
            and not self._entry_is_pinned_locked(key, entry)
        ]
        if completed:
            _, oldest_key = min(completed)
            self._entries.pop(oldest_key, None)
            self._remember_expired_locked(oldest_key)
            return
        raise LeaseProtocolError(
            "REPLAY_JOURNAL_FULL",
            "Authenticated request journal is full while protected entries remain",
        )

    def _bounded_response(
        self, request_id: str, response: Any, *, secrets: Sequence[str]
    ) -> Any:
        safe = redact_sensitive(scrub_exact_secrets(response, secrets))
        try:
            encoded = canonical_json_bytes(safe)
        except LeaseProtocolError:
            return completion_tombstone(request_id)
        if len(encoded) > self._response_max_bytes:
            return completion_tombstone(request_id)
        return safe


RequestReplayCache.__module__ = "rpc_server.lease_protocol"
