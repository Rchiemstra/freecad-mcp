"""MCP-side custody for document lease credentials.

Raw lease tokens deliberately live only in this module's in-memory records and
in the short-lived wire dictionaries produced for authenticated RPC calls.
Public status, reprs, and revocation records are always redacted.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import os
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


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
        default_factory=lambda: datetime.now(UTC).isoformat()
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
        if self.task_id:
            try:
                parsed_task_id = uuid.UUID(str(self.task_id))
            except (ValueError, AttributeError, TypeError) as exc:
                raise ValueError("task_id must be a UUID") from exc
            if parsed_task_id.int == 0:
                raise ValueError("task_id must not be the nil UUID")
            object.__setattr__(self, "task_id", str(parsed_task_id))

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

# Public alias for regression tests; STALE must never appear here.
REVOCATION_ERROR_CODES = _REVOCATION_ERROR_CODES

DEFAULT_STALE_AFTER_SECONDS = 90.0

# D8: stable orchestration reason codes (token-free).
STALE_RECOVERY_TRIGGER_HEARTBEAT = "heartbeat_stale_observed"
STALE_RECOVERY_TRIGGER_POST_TOOL = "post_tool_exceeded_stale_threshold"
STALE_RECOVERY_TRIGGER_PRE_OPERATION = "pre_operation_lazy"
STALE_RECOVERY_TRIGGER_RPC_REFUSAL = "rpc_stale_refusal"

STALE_RECOVERY_OUTCOME_RECOVERED = "recovered"
STALE_RECOVERY_OUTCOME_REFUSED_RETRYABLE = "refused_retryable"
STALE_RECOVERY_OUTCOME_REFUSED_TERMINAL = "refused_terminal"
STALE_RECOVERY_OUTCOME_SKIPPED_BACKOFF = "skipped_backoff"
STALE_RECOVERY_OUTCOME_SKIPPED_TERMINAL = "skipped_terminal"
STALE_RECOVERY_OUTCOME_SKIPPED_UNNECESSARY = "skipped_unnecessary"

STALE_RECOVERY_RETRY_ERROR_CODE = "LEASE_STALE_RECOVERED_RETRY"

_RECOVERY_EXEMPT_RPC_METHODS = frozenset(
    {
        "lease_heartbeat_batch",
        "lease_reconcile",
        "handshake_v2",
        "get_request_status",
        "claim_acquisition_result",
        "cancel_request",
    }
)
STALE_RECOVERY_EXEMPT_RPC_METHODS = _RECOVERY_EXEMPT_RPC_METHODS

_TERMINAL_RECONCILE_ERROR_CODES = frozenset(
    {
        "LEASE_AUTHORIZATION_FAILED",
        "LIVE_DOCUMENT_VALIDATION_FAILED",
        "LEASE_COORDINATION_LOST",
    }
)


def reconcile_refusal_is_terminal(response: Mapping[str, Any]) -> bool:
    """True when a lease_reconcile refusal should stop automatic recovery."""

    if not isinstance(response, Mapping):
        return False
    error_code = _upper_state(
        response.get("error_code") or response.get("code")
    )
    if error_code in _TERMINAL_RECONCILE_ERROR_CODES:
        return True
    if error_code == "LEASE_STATE_FORBIDS_OPERATION":
        state = heartbeat_item_lease_state(response)
        return state == "USER_INTERVENED"
    return False

_RECOVERY_BACKOFF_BASE_S = 2.0
_RECOVERY_BACKOFF_CAP_S = 60.0
_RECOVERY_BLOCKING_TIMEOUT_S = 120.0


def _upper_state(value: Any) -> str:
    return str(value or "").strip().upper()


def heartbeat_item_lease_state(item: Mapping[str, Any]) -> str:
    """Return the reported lease state from one heartbeat batch item."""

    state = _upper_state(item.get("state"))
    if state:
        return state
    lease = item.get("lease")
    if isinstance(lease, Mapping):
        state = _upper_state(lease.get("state"))
        if state:
            return state
    details = item.get("details")
    if isinstance(details, Mapping):
        return _upper_state(details.get("state"))
    return ""


def is_timeout_stale_heartbeat_item(item: Mapping[str, Any]) -> bool:
    """True when a heartbeat item reports a timeout-induced STALE lease."""

    if heartbeat_item_lease_state(item) == "STALE":
        return True
    error_code = _upper_state(item.get("error_code") or item.get("code"))
    if error_code != "LEASE_STATE_FORBIDS_OPERATION":
        return False
    return heartbeat_item_lease_state(item) == "STALE"


def _heartbeat_lease_items(response: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    """Return normalized lease items from one heartbeat batch response."""

    raw_results: Any = response.get("leases", response.get("results", ()))
    if isinstance(raw_results, Mapping):
        results: Sequence[Any] = tuple(raw_results.values())
    elif isinstance(raw_results, Sequence) and not isinstance(
        raw_results, (str, bytes)
    ):
        results = raw_results
    else:
        results = ()
    items: list[Mapping[str, Any]] = []
    for item in results:
        if isinstance(item, Mapping):
            items.append(item)
    return tuple(items)


def heartbeat_item_confirms_active_lease(item: Mapping[str, Any]) -> bool:
    """True when a heartbeat item proves the lease is still active (not STALE)."""

    if is_timeout_stale_heartbeat_item(item):
        return False
    if item.get("success") is False:
        return False
    state = heartbeat_item_lease_state(item)
    if not state:
        return item.get("success") is True
    if state == "STALE":
        return False
    return state.startswith("LOCKED_") or state == "ACQUIRING"


def extract_stale_sessions_from_heartbeat(
    response: Mapping[str, Any],
) -> tuple[str, ...]:
    """Collect held document session UUIDs reported as STALE by heartbeat."""

    stale: list[str] = []
    for item in _heartbeat_lease_items(response):
        if not is_timeout_stale_heartbeat_item(item):
            continue
        session_uuid = str(
            item.get("document_session_uuid") or item.get("session_uuid") or ""
        )
        if session_uuid:
            stale.append(session_uuid)
    return tuple(stale)


def extract_active_sessions_from_heartbeat(
    response: Mapping[str, Any],
) -> tuple[str, ...]:
    """Collect session UUIDs whose heartbeat item proves an active lease."""

    active: list[str] = []
    for item in _heartbeat_lease_items(response):
        if not heartbeat_item_confirms_active_lease(item):
            continue
        session_uuid = str(
            item.get("document_session_uuid") or item.get("session_uuid") or ""
        )
        if session_uuid:
            active.append(session_uuid)
    return tuple(active)


def reconcile_response_is_idempotent(response: Mapping[str, Any]) -> bool:
    """True when lease_reconcile succeeded without a STALE->LOCKED transition."""

    if not isinstance(response, Mapping) or not response.get("success"):
        return False
    if response.get("idempotent") is True:
        return True
    return response.get("already_active") is True


def rpc_response_indicates_stale_refusal(response: Mapping[str, Any]) -> bool:
    """True when an RPC envelope proves the lease blocked the call as STALE."""

    candidates: list[Mapping[str, Any]] = [response]
    result = response.get("result")
    if isinstance(result, Mapping):
        candidates.append(result)
    error = response.get("error")
    if isinstance(error, Mapping):
        candidates.append(error)

    for candidate in candidates:
        error_code = _upper_state(
            candidate.get("error_code") or candidate.get("code")
        )
        if error_code == "LEASE_STALE":
            return True
        if error_code == "LEASE_STATE_FORBIDS_OPERATION":
            state = heartbeat_item_lease_state(candidate)
            if state == "STALE":
                return True
            details = candidate.get("details")
            if isinstance(details, Mapping) and _upper_state(details.get("state")) == "STALE":
                return True
    return False


def rpc_response_mutation_may_have_begun(response: Mapping[str, Any]) -> bool:
    """Return whether the RPC layer recorded that a mutation may have started."""

    candidates: list[Mapping[str, Any]] = [response]
    result = response.get("result")
    if isinstance(result, Mapping):
        candidates.append(result)
    for candidate in candidates:
        if bool(candidate.get("mutation_may_have_begun")):
            return True
        details = candidate.get("details")
        if isinstance(details, Mapping) and bool(
            details.get("mutation_may_have_begun")
        ):
            return True
    return False


@dataclass(frozen=True, slots=True)
class StaleRecoveryResult:
    """Token-free outcome for one automatic stale-recovery attempt."""

    document_session_uuid: str
    trigger: str
    outcome: str
    reason_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        return stale_recovery_result_to_dict(self)


def stale_recovery_result_to_dict(result: StaleRecoveryResult) -> dict[str, Any]:
    """Return a stable, token-free stale-recovery status record."""

    attempted = result.outcome not in {
        STALE_RECOVERY_OUTCOME_SKIPPED_UNNECESSARY,
        STALE_RECOVERY_OUTCOME_SKIPPED_BACKOFF,
        STALE_RECOVERY_OUTCOME_SKIPPED_TERMINAL,
    }
    return {
        "document_session_uuid": result.document_session_uuid,
        "trigger": result.trigger,
        "outcome": result.outcome,
        "reason_code": result.reason_code,
        "attempted": attempted,
        "succeeded": result.outcome == STALE_RECOVERY_OUTCOME_RECOVERED,
        "refused": result.outcome
        in {
            STALE_RECOVERY_OUTCOME_REFUSED_RETRYABLE,
            STALE_RECOVERY_OUTCOME_REFUSED_TERMINAL,
        },
        "unnecessary": result.outcome == STALE_RECOVERY_OUTCOME_SKIPPED_UNNECESSARY,
    }


def summarize_stale_recovery_results(
    results: Mapping[str, StaleRecoveryResult],
) -> dict[str, Any]:
    """Summarize one batch of per-document stale-recovery outcomes."""

    sessions = [
        stale_recovery_result_to_dict(item)
        for _, item in sorted(results.items())
    ]
    if not sessions:
        return {
            "sessions": [],
            "attempted": False,
            "succeeded": False,
            "refused": False,
            "unnecessary": False,
        }
    return {
        "sessions": sessions,
        "attempted": any(item["attempted"] for item in sessions),
        "succeeded": any(item["succeeded"] for item in sessions),
        "refused": any(item["refused"] for item in sessions),
        "unnecessary": all(item["unnecessary"] for item in sessions),
    }


@dataclass(slots=True)
class _RecoveryAttemptState:
    attempt_count: int = 0
    last_attempt_monotonic: float = 0.0
    next_allowed_monotonic: float = 0.0
    terminal: bool = False
    terminal_reason_code: str = ""


class StaleLeaseRecoveryOrchestrator:
    """Serialize and bound exact-owner stale reconcile attempts per document."""

    def __init__(
        self,
        *,
        stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
        blocking_timeout_s: float = _RECOVERY_BLOCKING_TIMEOUT_S,
    ) -> None:
        self._stale_after_seconds = stale_after_seconds
        self._blocking_timeout_s = blocking_timeout_s
        self._needs_recovery: set[str] = set()
        self._heartbeat_active_at: dict[str, float] = {}
        self._attempts: dict[str, _RecoveryAttemptState] = {}
        self._last_results: dict[str, StaleRecoveryResult] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._meta_lock = asyncio.Lock()
        self._event_loop: asyncio.AbstractEventLoop | None = None

    @property
    def stale_after_seconds(self) -> float:
        return self._stale_after_seconds

    def bind_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._event_loop = loop

    def observe_heartbeat_batch(
        self, response: Mapping[str, Any]
    ) -> tuple[str, ...]:
        now = time.monotonic()
        stale = extract_stale_sessions_from_heartbeat(response)
        active = extract_active_sessions_from_heartbeat(response)
        for session_uuid in active:
            self._heartbeat_active_at[session_uuid] = now
            self._needs_recovery.discard(session_uuid)
        for session_uuid in stale:
            self._heartbeat_active_at.pop(session_uuid, None)
        self._needs_recovery.update(stale)
        return stale

    def observe_tool_completion(
        self,
        duration_s: float,
        session_uuids: Iterable[str],
    ) -> tuple[str, ...]:
        if duration_s < self._stale_after_seconds:
            return ()
        now = time.monotonic()
        freshness_deadline = now - self._stale_after_seconds
        affected: list[str] = []
        for session_uuid in dict.fromkeys(
            str(item) for item in session_uuids if item
        ):
            if session_uuid in self._needs_recovery:
                affected.append(session_uuid)
                continue
            last_active = self._heartbeat_active_at.get(session_uuid)
            if last_active is not None and last_active >= freshness_deadline:
                continue
            affected.append(session_uuid)
        self._needs_recovery.update(affected)
        return tuple(affected)

    def sessions_needing_recovery(
        self, session_uuids: Iterable[str]
    ) -> tuple[str, ...]:
        return tuple(
            session_uuid
            for session_uuid in dict.fromkeys(
                str(item) for item in session_uuids if item
            )
            if session_uuid in self._needs_recovery
        )

    def mark_needs_recovery(self, session_uuid: str) -> None:
        if session_uuid:
            self._needs_recovery.add(session_uuid)

    def last_recovery_results(self) -> dict[str, StaleRecoveryResult]:
        return dict(self._last_results)

    def recovery_status_snapshot(self) -> dict[str, Any]:
        return summarize_stale_recovery_results(self._last_results)

    def recovery_status_snapshot_for(
        self, session_uuids: Iterable[str]
    ) -> dict[str, Any]:
        allowed = {str(item) for item in session_uuids if item}
        if not allowed:
            return summarize_stale_recovery_results({})
        filtered = {
            key: value
            for key, value in self._last_results.items()
            if key in allowed
        }
        return summarize_stale_recovery_results(filtered)

    def _record_recovery_result(self, result: StaleRecoveryResult) -> None:
        existing = self._last_results.get(result.document_session_uuid)
        if (
            existing is not None
            and existing.outcome == STALE_RECOVERY_OUTCOME_RECOVERED
            and result.outcome == STALE_RECOVERY_OUTCOME_SKIPPED_UNNECESSARY
        ):
            return
        self._last_results[result.document_session_uuid] = result

    async def _lock_for(self, session_uuid: str) -> asyncio.Lock:
        async with self._meta_lock:
            lock = self._locks.get(session_uuid)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[session_uuid] = lock
            return lock

    async def recover_sessions(
        self,
        session_uuids: Iterable[str],
        trigger: str,
        reconcile_fn: Callable[[str], Mapping[str, Any]],
    ) -> dict[str, StaleRecoveryResult]:
        results: dict[str, StaleRecoveryResult] = {}
        for session_uuid in dict.fromkeys(
            str(item) for item in session_uuids if item
        ):
            lock = await self._lock_for(session_uuid)
            async with lock:
                results[session_uuid] = await self._recover_one_locked(
                    session_uuid,
                    trigger,
                    reconcile_fn,
                )
        return results

    async def _recover_one_locked(
        self,
        session_uuid: str,
        trigger: str,
        reconcile_fn: Callable[[str], Mapping[str, Any]],
    ) -> StaleRecoveryResult:
        attempt_state = self._attempts.get(session_uuid)
        if attempt_state is not None and attempt_state.terminal:
            result = StaleRecoveryResult(
                document_session_uuid=session_uuid,
                trigger=trigger,
                outcome=STALE_RECOVERY_OUTCOME_SKIPPED_TERMINAL,
                reason_code=attempt_state.terminal_reason_code or "TERMINAL",
            )
            self._record_recovery_result(result)
            return result
        if session_uuid not in self._needs_recovery:
            result = StaleRecoveryResult(
                document_session_uuid=session_uuid,
                trigger=trigger,
                outcome=STALE_RECOVERY_OUTCOME_SKIPPED_UNNECESSARY,
            )
            self._record_recovery_result(result)
            return result
        now = time.monotonic()
        if attempt_state is not None and now < attempt_state.next_allowed_monotonic:
            result = StaleRecoveryResult(
                document_session_uuid=session_uuid,
                trigger=trigger,
                outcome=STALE_RECOVERY_OUTCOME_SKIPPED_BACKOFF,
                reason_code="BACKOFF",
            )
            self._record_recovery_result(result)
            return result

        try:
            response = await asyncio.to_thread(reconcile_fn, session_uuid)
        except Exception:
            response = {
                "success": False,
                "error_code": "RECONCILE_TRANSPORT_ERROR",
            }
        error_code = _upper_state(
            response.get("error_code")
            if isinstance(response, Mapping)
            else ""
        )
        if isinstance(response, Mapping) and response.get("success"):
            self._needs_recovery.discard(session_uuid)
            if reconcile_response_is_idempotent(response):
                result = StaleRecoveryResult(
                    document_session_uuid=session_uuid,
                    trigger=trigger,
                    outcome=STALE_RECOVERY_OUTCOME_SKIPPED_UNNECESSARY,
                    reason_code="ALREADY_ACTIVE",
                )
                self._record_recovery_result(result)
                return result
            self._attempts.pop(session_uuid, None)
            self._heartbeat_active_at[session_uuid] = now
            result = StaleRecoveryResult(
                document_session_uuid=session_uuid,
                trigger=trigger,
                outcome=STALE_RECOVERY_OUTCOME_RECOVERED,
            )
            self._record_recovery_result(result)
            return result
        if isinstance(response, Mapping) and reconcile_refusal_is_terminal(response):
            self._attempts[session_uuid] = _RecoveryAttemptState(
                terminal=True,
                terminal_reason_code=error_code,
            )
            self._needs_recovery.discard(session_uuid)
            result = StaleRecoveryResult(
                document_session_uuid=session_uuid,
                trigger=trigger,
                outcome=STALE_RECOVERY_OUTCOME_REFUSED_TERMINAL,
                reason_code=error_code,
            )
            self._record_recovery_result(result)
            return result

        attempt_count = (attempt_state.attempt_count if attempt_state else 0) + 1
        backoff = min(
            _RECOVERY_BACKOFF_CAP_S,
            _RECOVERY_BACKOFF_BASE_S * (2 ** (attempt_count - 1)),
        )
        self._attempts[session_uuid] = _RecoveryAttemptState(
            attempt_count=attempt_count,
            last_attempt_monotonic=now,
            next_allowed_monotonic=now + backoff,
        )
        result = StaleRecoveryResult(
            document_session_uuid=session_uuid,
            trigger=trigger,
            outcome=STALE_RECOVERY_OUTCOME_REFUSED_RETRYABLE,
            reason_code=error_code or "RECONCILE_REFUSED",
        )
        self._record_recovery_result(result)
        return result

    def recover_sessions_blocking(
        self,
        session_uuids: Iterable[str],
        trigger: str,
        reconcile_fn: Callable[[str], Mapping[str, Any]],
    ) -> dict[str, StaleRecoveryResult]:
        sessions = self.sessions_needing_recovery(session_uuids)
        if not sessions:
            return {}
        coro = self.recover_sessions(sessions, trigger, reconcile_fn)
        loop = self._event_loop
        if loop is None:
            return asyncio.run(coro)
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result(timeout=self._blocking_timeout_s)
        return loop.run_until_complete(coro)


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
            self._disconnected_at = datetime.now(UTC).isoformat()

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
            self._disconnected_at = datetime.now(UTC).isoformat()

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
