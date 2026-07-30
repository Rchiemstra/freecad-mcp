"""Async LOCKED_ERROR automatic handoff state.

Detect returns immediately with ``LOCKED_ERROR_HANDOFF_PENDING``. A background
continuation performs bounded GUI authorization/revalidation and hash/CAS work,
then stores the credential in the acquisition claim vault for control-lane
polling. No agent-start dialog is opened.

``cancel_request`` can abort the continuation only before ``begin_claim``.
After that irreversible transition (or vault escrow), cancel returns
not-cancellable and ownership rotation proceeds. Terminal failed/denied/
claimed states return their actual continuation details instead of
``not_cancellable``.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Literal

HandoffCancelStatus = Literal[
    "not_found",
    "cancelled",
    "already_cancelled",
    "not_cancellable",
    "terminal_failed",
    "terminal_denied",
    "already_claimed",
]


@dataclass
class HandoffContinuation:
    mcp_runtime_id: str
    request_id: str
    state: str = "pending_authorization"
    stage: str = "handoff_authorize"
    error_code: str | None = None
    error: str | None = None
    cancel_requested: threading.Event = field(default_factory=threading.Event)
    created_monotonic: float = field(default_factory=time.monotonic)
    updated_monotonic: float = field(default_factory=time.monotonic)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "stage": self.stage,
            # Retained for wire compatibility. Handoff is now auto-authorized.
            "confirmation_pending": False,
            "handoff_pending": self.state
            in {
                "pending_authorization",
                "authorizing",
                "hashing",
                "claiming",
                "claim_committed",
                "claiming_uncertain",
            },
            "cancellation_requested": self.cancel_requested.is_set(),
            "error_code": self.error_code,
            "error": self.error,
        }


class HandoffContinuationStore:
    """Process-local map of in-flight LOCKED_ERROR handoff continuations."""

    ACTIVE = frozenset(
        {
            "pending_authorization",
            "authorizing",
            "hashing",
            "claiming",
            "claim_committed",
            "claiming_uncertain",
        }
    )
    # Cancel cannot win once CAS is authorized or escrowed.
    IRREVERSIBLE = frozenset(
        {"claim_committed", "claimable", "claiming_uncertain"}
    )
    PRE_CLAIM = frozenset(
        {"pending_authorization", "authorizing", "hashing", "claiming"}
    )
    TERMINAL = frozenset(
        {"cancelled", "failed", "denied", "claimed", "claimable"}
    )

    def __init__(self, *, ttl_seconds: float = 3600.0) -> None:
        self._ttl_seconds = float(ttl_seconds)
        self._entries: dict[tuple[str, str], HandoffContinuation] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _key(mcp_runtime_id: str, request_id: str) -> tuple[str, str]:
        return str(mcp_runtime_id or ""), str(request_id or "")

    def begin(
        self, *, mcp_runtime_id: str, request_id: str
    ) -> HandoffContinuation:
        key = self._key(mcp_runtime_id, request_id)
        if not key[0] or not key[1]:
            raise ValueError("mcp_runtime_id and request_id are required")
        entry = HandoffContinuation(
            mcp_runtime_id=key[0], request_id=key[1]
        )
        with self._lock:
            self._entries[key] = entry
        return entry

    def get(
        self, mcp_runtime_id: str, request_id: str
    ) -> HandoffContinuation | None:
        key = self._key(mcp_runtime_id, request_id)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if (
                entry.state not in self.ACTIVE
                and (time.monotonic() - entry.updated_monotonic)
                > self._ttl_seconds
            ):
                self._entries.pop(key, None)
                return None
            return entry

    def update(
        self,
        mcp_runtime_id: str,
        request_id: str,
        *,
        state: str,
        stage: str | None = None,
        error_code: str | None = None,
        error: str | None = None,
    ) -> HandoffContinuation | None:
        key = self._key(mcp_runtime_id, request_id)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            # Escrow wins over cancel/fail races; claim_committed may still
            # become terminal failed/denied if CAS/validation aborts after the
            # cancel gate (no credential escrowed yet). Claimable may move to
            # claimed after custody acknowledgement or to failed when escrow
            # expires/disappears before claim.
            if entry.state == "claimable" and state not in {
                "claimable",
                "claimed",
                "failed",
            }:
                return entry
            if entry.state == "claimed" and state != "claimed":
                return entry
            if entry.state == "claim_committed" and state in {
                "cancelled",
                "pending_authorization",
                "authorizing",
                "hashing",
                "claiming",
            }:
                return entry
            if entry.state == "cancelled" and state not in {
                "claimable",
                "cancelled",
            }:
                # Ignore mid-flight stage updates after cancel (except escrow).
                return entry
            entry.state = state
            if stage is not None:
                entry.stage = stage
            if state in {"claimable", "claimed"}:
                entry.error_code = None
                entry.error = None
            else:
                entry.error_code = error_code
                entry.error = error
            entry.updated_monotonic = time.monotonic()
            return entry

    def begin_claim(self, mcp_runtime_id: str, request_id: str) -> bool:
        """Atomically authorize CAS; False if cancel already won.

        Once this returns True, ``request_cancel`` reports not-cancellable and
        the continuation may perform ownership rotation.
        """

        key = self._key(mcp_runtime_id, request_id)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return False
            if entry.state in self.IRREVERSIBLE:
                return True
            if entry.state == "cancelled" or entry.cancel_requested.is_set():
                if entry.state != "cancelled":
                    entry.state = "cancelled"
                    entry.stage = "handoff_cancelled"
                    entry.error_code = "LOCKED_ERROR_HANDOFF_CANCELLED"
                    entry.error = (
                        "LOCKED_ERROR handoff was cancelled before ownership "
                        "rotation"
                    )
                    entry.updated_monotonic = time.monotonic()
                return False
            if entry.state not in self.PRE_CLAIM and entry.state not in self.ACTIVE:
                return False
            entry.state = "claim_committed"
            entry.stage = "acquisition_claim"
            entry.error_code = None
            entry.error = None
            entry.updated_monotonic = time.monotonic()
            return True

    def request_cancel(
        self, mcp_runtime_id: str, request_id: str
    ) -> HandoffCancelStatus:
        """Attempt to cancel a pre-CAS handoff continuation.

        Returns:
            ``cancelled`` / ``already_cancelled`` when abort succeeded,
            ``not_cancellable`` after ``begin_claim`` or escrow,
            ``terminal_failed`` / ``terminal_denied`` for terminal outcomes,
            ``already_claimed`` after custody acknowledgement,
            ``not_found`` when no continuation exists.
        """

        key = self._key(mcp_runtime_id, request_id)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return "not_found"
            if entry.state in self.IRREVERSIBLE:
                return "not_cancellable"
            if entry.state == "failed":
                return "terminal_failed"
            if entry.state == "denied":
                return "terminal_denied"
            if entry.state == "claimed":
                return "already_claimed"
            if entry.state == "cancelled":
                entry.cancel_requested.set()
                return "already_cancelled"
            entry.cancel_requested.set()
            if entry.state in self.PRE_CLAIM or entry.state in self.ACTIVE:
                entry.state = "cancelled"
                entry.stage = "handoff_cancelled"
                entry.error_code = "LOCKED_ERROR_HANDOFF_CANCELLED"
                entry.error = (
                    "LOCKED_ERROR handoff was cancelled before ownership rotation"
                )
                entry.updated_monotonic = time.monotonic()
                return "cancelled"
            return "not_cancellable"

    def is_cancelled(self, mcp_runtime_id: str, request_id: str) -> bool:
        entry = self.get(mcp_runtime_id, request_id)
        if entry is None:
            return False
        if entry.state in self.IRREVERSIBLE or entry.state == "claimed":
            return False
        return entry.cancel_requested.is_set() or entry.state == "cancelled"

    def discard(self, mcp_runtime_id: str, request_id: str) -> bool:
        key = self._key(mcp_runtime_id, request_id)
        with self._lock:
            return self._entries.pop(key, None) is not None
