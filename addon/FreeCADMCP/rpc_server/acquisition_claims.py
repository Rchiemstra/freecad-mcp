"""Private claim vault for acquisition credentials after response loss.

Successful acquire/adopt/create responses deliberately omit the raw token from
the replay cache. When the first XML-RPC response is lost, the authenticated
MCP runtime that initiated the request may retrieve the credential repeatedly
until it acknowledges custody. Unacknowledged entries are never expired,
evicted, or rejected at the configured soft capacity: preserving the only raw
credential takes precedence over a process-local memory target. Public status
never includes the token.
"""

from __future__ import annotations

import copy
import threading
import time
from collections import OrderedDict
from typing import Any

from .acquisition_claims_types.claim_entry import ClaimEntry


class AcquisitionClaimStore:
    """Process-local vault for durable acquisition credential retrieval."""

    def __init__(
        self,
        *,
        max_entries: int = 256,
        ttl_seconds: float = 600.0,
        monotonic: Any = time.monotonic,
    ) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._max_entries = int(max_entries)
        self._ttl_seconds = float(ttl_seconds)
        self._monotonic = monotonic
        self._entries: OrderedDict[tuple[str, str], ClaimEntry] = OrderedDict()
        self._lock = threading.RLock()

    @staticmethod
    def _key(mcp_runtime_id: str, request_id: str) -> tuple[str, str]:
        runtime = str(mcp_runtime_id or "")
        request = str(request_id or "")
        if not runtime or not request:
            raise ValueError("mcp_runtime_id and request_id are required")
        return runtime, request

    def _prune_locked(self, now: float) -> None:
        # ``ttl_seconds`` remains a validated constructor option for backward
        # compatibility, but it must never expire an unacknowledged credential.
        # A lease may remain unresolved well beyond the old ten-minute TTL.
        del now
        acknowledged = [
            key
            for key, entry in self._entries.items()
            if entry.acknowledged
        ]
        for key in acknowledged:
            self._entries.pop(key, None)

    def store(
        self,
        *,
        mcp_runtime_id: str,
        request_id: str,
        method: str,
        credential: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        """Retain one private credential until acknowledgement or exact use."""

        token = str((credential or {}).get("token") or "")
        if not token or token == "[REDACTED]":
            raise ValueError("acquisition claim requires a raw credential token")
        key = self._key(mcp_runtime_id, request_id)
        now = float(self._monotonic())
        with self._lock:
            self._prune_locked(now)
            # ``max_entries`` is deliberately a soft capacity. A generic
            # acquire/adopt/create may have already published authority by the
            # time it reaches this vault; rejecting or evicting here would
            # strand that authority without its only raw credential.
            self._entries[key] = ClaimEntry(
                mcp_runtime_id=key[0],
                request_id=key[1],
                method=str(method),
                credential=copy.deepcopy(dict(credential)),
                result=copy.deepcopy(dict(result)),
                created_monotonic=now,
            )
            self._entries.move_to_end(key)

    def claimable(self, mcp_runtime_id: str, request_id: str) -> bool:
        key = self._key(mcp_runtime_id, request_id)
        now = float(self._monotonic())
        with self._lock:
            self._prune_locked(now)
            entry = self._entries.get(key)
            return entry is not None and not entry.acknowledged

    def public_status(self, mcp_runtime_id: str, request_id: str) -> dict[str, Any]:
        """Redacted claim status; never includes a token or fingerprint."""

        key = self._key(mcp_runtime_id, request_id)
        now = float(self._monotonic())
        with self._lock:
            self._prune_locked(now)
            entry = self._entries.get(key)
            if entry is None:
                return {"claimable": False}
            return {
                "claimable": not entry.acknowledged,
                "method": entry.method,
                "lease_id": entry.credential.get("lease_id"),
                "document_session_uuid": entry.credential.get(
                    "document_session_uuid"
                ),
                "generation": entry.credential.get("generation"),
            }

    def claim(self, mcp_runtime_id: str, request_id: str) -> dict[str, Any] | None:
        """Peek the private result without scrubbing.

        Repeatable until ``acknowledge`` so a lost claim response remains
        recoverable for the same authenticated runtime.
        """

        key = self._key(mcp_runtime_id, request_id)
        now = float(self._monotonic())
        with self._lock:
            self._prune_locked(now)
            entry = self._entries.get(key)
            if entry is None or entry.acknowledged:
                return None
            payload = copy.deepcopy(entry.result)
            credential = copy.deepcopy(entry.credential)
        payload["credential"] = credential
        payload["success"] = True
        return payload

    def acknowledge(self, mcp_runtime_id: str, request_id: str) -> bool:
        """Scrub the vault after the client has custodied the credential."""

        key = self._key(mcp_runtime_id, request_id)
        with self._lock:
            entry = self._entries.pop(key, None)
            if entry is None:
                return False
            entry.acknowledged = True
            return True

    def acknowledge_credential(
        self,
        *,
        mcp_runtime_id: str,
        lease_id: str,
        document_session_uuid: str,
        generation: int,
        token: str,
    ) -> bool:
        """Auto-ack when the owning runtime first uses the exact credential."""

        runtime = str(mcp_runtime_id or "")
        if not runtime or not token:
            return False
        with self._lock:
            for key, entry in list(self._entries.items()):
                if key[0] != runtime or entry.acknowledged:
                    continue
                credential = entry.credential
                if (
                    str(credential.get("lease_id") or "") == str(lease_id)
                    and str(credential.get("document_session_uuid") or "")
                    == str(document_session_uuid)
                    and int(credential.get("generation") or -1) == int(generation)
                    and str(credential.get("token") or "") == str(token)
                ):
                    self._entries.pop(key, None)
                    return True
        return False

    def discard(self, mcp_runtime_id: str, request_id: str) -> bool:
        key = self._key(mcp_runtime_id, request_id)
        with self._lock:
            return self._entries.pop(key, None) is not None
