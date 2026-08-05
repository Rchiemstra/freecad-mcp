"""Process-wide authenticated request cancellation and completion tracking."""

from __future__ import annotations

import threading as _threading
from collections import OrderedDict as _OrderedDict
from typing import Any as _Any

from .cancellation_result import CancellationResult as _CancellationResult
from .cancellation_token import CancellationToken as _CancellationToken
from .inflight_request import InflightRequest as _InflightRequest
from .inflight_snapshot import InflightSnapshot as _InflightSnapshot


class InflightRequestRegistry:
    """Own active request state and bounded redacted terminal tombstones."""

    def __init__(self, *, max_terminal_entries: int = 4096) -> None:
        if max_terminal_entries <= 0:
            raise ValueError("max_terminal_entries must be positive")
        self._max_terminal_entries = int(max_terminal_entries)
        self._active: dict[tuple[str, str], _InflightRequest] = {}
        self._terminal: _OrderedDict[tuple[str, str], _InflightRequest] = _OrderedDict()
        self._lock = _threading.RLock()

    @staticmethod
    def _key(session_id: str, request_id: str) -> tuple[str, str]:
        session = str(session_id or "")
        request = str(request_id or "")
        if not session or not request:
            raise ValueError("session_id and request_id are required")
        return session, request

    def register(
        self,
        session_id: str,
        request_id: str,
        method: str,
    ) -> _InflightRequest:
        key = self._key(session_id, request_id)
        with self._lock:
            if key in self._active or key in self._terminal:
                raise ValueError("authenticated request is already registered")
            request = _InflightRequest(
                session_id=key[0],
                request_id=key[1],
                method=str(method),
                token=_CancellationToken(key[0], key[1], str(method)),
            )
            self._active[key] = request
            return request

    def get(self, session_id: str, request_id: str) -> _InflightRequest | None:
        key = self._key(session_id, request_id)
        with self._lock:
            return self._active.get(key) or self._terminal.get(key)

    def request_cancel(self, session_id: str, request_id: str) -> _CancellationResult:
        key = self._key(session_id, request_id)
        with self._lock:
            request = self._active.get(key)
            if request is None:
                terminal = self._terminal.get(key)
                if terminal is None:
                    return _CancellationResult("unknown", None)
                return _CancellationResult("completed", terminal.token.snapshot())
            newly_requested, snapshot = request.token.request_cancel()
            if not newly_requested and not snapshot.cancellation_requested:
                return _CancellationResult("not_cancellable", snapshot)
            return _CancellationResult(
                "requested" if newly_requested else "already_requested", snapshot
            )

    def begin_gui_phase(
        self, session_id: str, request_id: str, phase: str
    ) -> _CancellationToken | None:
        key = self._key(session_id, request_id)
        with self._lock:
            request = self._active.get(key)
            if request is None:
                return None
            request.token.begin_gui_phase(phase)
            return request.token

    def end_gui_phase(self, session_id: str, request_id: str) -> _InflightSnapshot | None:
        key = self._key(session_id, request_id)
        with self._lock:
            request = self._active.get(key)
            if request is None:
                return None
            snapshot = request.token.end_gui_phase()
            self._terminalize_locked(key, request, snapshot)
            return snapshot

    def finish_handler(
        self, session_id: str, request_id: str, *, status: str
    ) -> _InflightSnapshot | None:
        key = self._key(session_id, request_id)
        with self._lock:
            request = self._active.get(key)
            if request is None:
                terminal = self._terminal.get(key)
                return terminal.token.snapshot() if terminal is not None else None
            snapshot = request.token.finish_handler(status)
            self._terminalize_locked(key, request, snapshot)
            return snapshot

    def _terminalize_locked(
        self,
        key: tuple[str, str],
        request: _InflightRequest,
        snapshot: _InflightSnapshot,
    ) -> None:
        if not snapshot.terminal:
            return
        self._active.pop(key, None)
        self._terminal[key] = request
        self._terminal.move_to_end(key)
        while len(self._terminal) > self._max_terminal_entries:
            self._terminal.popitem(last=False)

    def status(self, session_id: str, request_id: str) -> _InflightSnapshot | None:
        request = self.get(session_id, request_id)
        return request.token.snapshot() if request is not None else None

    def latest_recovery_incident(
        self, session_id: str | None = None
    ) -> _InflightSnapshot | None:
        """Return the newest visible uncertain/recovered request tombstone."""

        with self._lock:
            requests = [*self._active.values(), *reversed(self._terminal.values())]
            for request in requests:
                snapshot = request.token.snapshot()
                if (
                    snapshot.recovery_incident_id
                    and (session_id is None or snapshot.session_id == session_id)
                ):
                    return snapshot
        return None

    def refresh_terminal(
        self, session_id: str, request_id: str
    ) -> _InflightSnapshot | None:
        """Move a token terminalized by cancellation resolution to tombstones."""

        key = self._key(session_id, request_id)
        with self._lock:
            request = self._active.get(key)
            if request is None:
                terminal = self._terminal.get(key)
                return terminal.token.snapshot() if terminal is not None else None
            snapshot = request.token.snapshot()
            self._terminalize_locked(key, request, snapshot)
            return snapshot

    def finish_cancellation_resolution(
        self,
        request: _InflightRequest,
        result: _Any,
    ) -> _Any:
        """Publish a cancellation result and atomically retire a terminal request."""

        key = self._key(request.session_id, request.request_id)
        with self._lock:
            registered = self._active.get(key) or self._terminal.get(key)
            if registered is not request:
                raise ValueError("cancellation request is not registered")
            resolved = request.token.finish_cancellation_resolution(result)
            self._terminalize_locked(key, request, request.token.snapshot())
            return resolved

    def request_cancel_all(self) -> tuple[_InflightRequest, ...]:
        """Signal every active request during process/listener shutdown."""

        with self._lock:
            requests = tuple(self._active.values())
            for request in requests:
                request.token.request_cancel()
            return requests

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._active)
