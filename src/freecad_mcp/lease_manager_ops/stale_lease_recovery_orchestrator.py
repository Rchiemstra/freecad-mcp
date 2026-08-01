"""StaleLeaseRecoveryOrchestrator — extracted from lease_manager."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from .heartbeat_helpers import (
    extract_active_sessions_from_heartbeat,
    extract_stale_sessions_from_heartbeat,
)
from .recovery_attempt_state import RecoveryAttemptState
from .stale_recovery_constants import (
    _RECOVERY_BACKOFF_BASE_S,
    _RECOVERY_BACKOFF_CAP_S,
    _RECOVERY_BLOCKING_TIMEOUT_S,
    DEFAULT_STALE_AFTER_SECONDS,
    STALE_RECOVERY_OUTCOME_RECOVERED,
    STALE_RECOVERY_OUTCOME_REFUSED_RETRYABLE,
    STALE_RECOVERY_OUTCOME_REFUSED_TERMINAL,
    STALE_RECOVERY_OUTCOME_SKIPPED_BACKOFF,
    STALE_RECOVERY_OUTCOME_SKIPPED_TERMINAL,
    STALE_RECOVERY_OUTCOME_SKIPPED_UNNECESSARY,
    _upper_state,
)
from .stale_recovery_helpers import (
    reconcile_refusal_is_terminal,
    reconcile_response_is_idempotent,
    summarize_stale_recovery_results,
)
from .stale_recovery_result import StaleRecoveryResult


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
        self._attempts: dict[str, RecoveryAttemptState] = {}
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
            self._attempts[session_uuid] = RecoveryAttemptState(
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
        self._attempts[session_uuid] = RecoveryAttemptState(
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
