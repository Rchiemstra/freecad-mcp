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

import time
from collections.abc import Callable
from typing import Literal

from .handoff_continuations_types.handoff_continuation import HandoffContinuation

try:
    from ..dispatch.continuations import BoundedContinuationRegistry
except ImportError:  # pragma: no cover - flat FreeCAD add-on import path
    from dispatch.continuations import BoundedContinuationRegistry

HandoffCancelStatus = Literal[
    "not_found",
    "cancelled",
    "already_cancelled",
    "not_cancellable",
    "terminal_failed",
    "terminal_denied",
    "already_claimed",
]


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

    def __init__(
        self,
        *,
        ttl_seconds: float = 3600.0,
        max_entries: int = 4096,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._monotonic = monotonic
        self._registry: BoundedContinuationRegistry[
            tuple[str, str], HandoffContinuation
        ] = BoundedContinuationRegistry(
            max_entries=max_entries,
            ttl_seconds=ttl_seconds,
            monotonic=monotonic,
            is_protected=lambda entry: entry.state in self.ACTIVE
            or entry.state in self.IRREVERSIBLE,
            is_expiry_protected=lambda entry: entry.state in self.ACTIVE,
        )

    @staticmethod
    def _key(mcp_runtime_id: str, request_id: str) -> tuple[str, str]:
        return str(mcp_runtime_id or ""), str(request_id or "")

    def begin(
        self, *, mcp_runtime_id: str, request_id: str
    ) -> HandoffContinuation:
        key = self._key(mcp_runtime_id, request_id)
        if not key[0] or not key[1]:
            raise ValueError("mcp_runtime_id and request_id are required")
        now = float(self._monotonic())
        entry = HandoffContinuation(
            mcp_runtime_id=key[0],
            request_id=key[1],
            created_monotonic=now,
            updated_monotonic=now,
        )
        return self._registry.begin(key, entry)

    def get(
        self, mcp_runtime_id: str, request_id: str
    ) -> HandoffContinuation | None:
        key = self._key(mcp_runtime_id, request_id)
        return self._registry.get(key)

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
        def apply_update(entry: HandoffContinuation) -> HandoffContinuation:
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
            entry.updated_monotonic = float(self._monotonic())
            return entry

        try:
            return self._registry.apply(key, apply_update)
        except KeyError:
            return None

    def begin_claim(self, mcp_runtime_id: str, request_id: str) -> bool:
        """Atomically authorize CAS; False if cancel already won.

        Once this returns True, ``request_cancel`` reports not-cancellable and
        the continuation may perform ownership rotation.
        """

        key = self._key(mcp_runtime_id, request_id)
        def claim(entry: HandoffContinuation) -> bool:
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
                    entry.updated_monotonic = float(self._monotonic())
                return False
            if entry.state not in self.PRE_CLAIM and entry.state not in self.ACTIVE:
                return False
            entry.state = "claim_committed"
            entry.stage = "acquisition_claim"
            entry.error_code = None
            entry.error = None
            entry.updated_monotonic = float(self._monotonic())
            return True

        try:
            return self._registry.apply(key, claim)
        except KeyError:
            return False

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
        def cancel(entry: HandoffContinuation) -> HandoffCancelStatus:
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
                entry.updated_monotonic = float(self._monotonic())
                return "cancelled"
            return "not_cancellable"

        try:
            return self._registry.apply(key, cancel)
        except KeyError:
            return "not_found"

    def is_cancelled(self, mcp_runtime_id: str, request_id: str) -> bool:
        entry = self.get(mcp_runtime_id, request_id)
        if entry is None:
            return False
        if entry.state in self.IRREVERSIBLE or entry.state == "claimed":
            return False
        return entry.cancel_requested.is_set() or entry.state == "cancelled"

    def discard(self, mcp_runtime_id: str, request_id: str) -> bool:
        key = self._key(mcp_runtime_id, request_id)
        return self._registry.discard(key)

    @property
    def entry_count(self) -> int:
        """Return retained continuations after bounded expiry cleanup."""

        return self._registry.count
