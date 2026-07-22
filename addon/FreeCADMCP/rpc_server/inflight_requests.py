"""Process-wide authenticated request cancellation and completion tracking.

The registry deliberately has no FreeCAD or Qt dependency.  It spans the
whole ``invoke_v2`` lifetime, including filesystem/worker gaps and GUI work
that finishes after its XML-RPC handler has returned.
"""

from __future__ import annotations

import copy
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Iterable


class RequestCancellationError(RuntimeError):
    """Raised at a cooperative phase boundary after cancellation was requested."""

    code = "REQUEST_CANCELLED"

    def __init__(self, snapshot: "InflightSnapshot") -> None:
        self.snapshot = snapshot
        suffix = (
            " after document mutation may have begun"
            if snapshot.mutation_started or snapshot.uncertain
            else " before document mutation began"
        )
        super().__init__(f"authenticated request was cancelled{suffix}")


@dataclass(frozen=True)
class InflightLeaseCredential:
    """Private request credential; its bearer token is never represented."""

    lease_id: str
    document_session_uuid: str
    generation: int
    token: str = field(repr=False)
    mcp_instance_id: str = ""


@dataclass(frozen=True)
class InflightSnapshot:
    session_id: str
    request_id: str
    method: str
    phase: str
    cancellation_requested: bool
    mutation_started: bool
    uncertain: bool
    handler_finished: bool
    active_gui_phases: int
    terminal: bool
    terminal_status: str | None
    cancel_requested_at: float | None
    cancellation_resolved: bool

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "method": self.method,
            "phase": self.phase,
            "cancellation_requested": self.cancellation_requested,
            "mutation_started": self.mutation_started,
            "uncertain": self.uncertain,
            "handler_finished": self.handler_finished,
            "active_gui_phases": self.active_gui_phases,
            "terminal": self.terminal,
            "terminal_status": self.terminal_status,
            "cancellation_resolved": self.cancellation_resolved,
        }


class CancellationToken:
    """Thread-safe mutable state shared by all phases of one RPC request."""

    def __init__(self, session_id: str, request_id: str, method: str) -> None:
        self.session_id = str(session_id)
        self.request_id = str(request_id)
        self.method = str(method)
        self._phase = "registered"
        self._cancellation_requested = False
        self._mutation_started = False
        self._uncertain = False
        self._handler_finished = False
        self._active_gui_phases = 0
        self._terminal = False
        self._terminal_status: str | None = None
        self._cancel_requested_at: float | None = None
        self._accepting_cancellation = True
        self._cancellation_resolving = False
        self._cancellation_resolved = False
        self._cancellation_resolution: Any = None
        self._cancellation_resolution_complete = threading.Event()
        self._cancellation_begin_claimed = False
        self._cancellation_begin_complete = threading.Event()
        self._lock = threading.RLock()

    def _snapshot_locked(self) -> InflightSnapshot:
        return InflightSnapshot(
            session_id=self.session_id,
            request_id=self.request_id,
            method=self.method,
            phase=self._phase,
            cancellation_requested=self._cancellation_requested,
            mutation_started=self._mutation_started,
            uncertain=self._uncertain,
            handler_finished=self._handler_finished,
            active_gui_phases=self._active_gui_phases,
            terminal=self._terminal,
            terminal_status=self._terminal_status,
            cancel_requested_at=self._cancel_requested_at,
            cancellation_resolved=self._cancellation_resolved,
        )

    def snapshot(self) -> InflightSnapshot:
        with self._lock:
            return self._snapshot_locked()

    def set_phase(self, phase: str) -> InflightSnapshot:
        with self._lock:
            if not self._terminal:
                self._phase = str(phase)[:128]
            return self._snapshot_locked()

    def checkpoint(self, phase: str) -> InflightSnapshot:
        """Publish *phase* and fail before starting it when cancelled."""

        with self._lock:
            if not self._terminal:
                self._phase = str(phase)[:128]
            snapshot = self._snapshot_locked()
        if snapshot.cancellation_requested:
            raise RequestCancellationError(snapshot)
        return snapshot

    def request_cancel(self) -> tuple[bool, InflightSnapshot]:
        with self._lock:
            newly_requested = (
                not self._cancellation_requested
                and not self._terminal
                and self._accepting_cancellation
            )
            if not self._terminal and self._accepting_cancellation:
                self._cancellation_requested = True
                if self._cancel_requested_at is None:
                    self._cancel_requested_at = time.monotonic()
            return newly_requested, self._snapshot_locked()

    def mark_mutation_started(self, phase: str = "mutation_started") -> InflightSnapshot:
        """Conservatively record that document or file mutation may now occur."""

        with self._lock:
            self._mutation_started = True
            self._phase = str(phase)[:128]
            return self._snapshot_locked()

    def begin_mutation(self, phase: str = "mutation_started") -> InflightSnapshot:
        """Atomically reject cancellation or cross the may-mutate boundary."""

        with self._lock:
            if self._cancellation_requested:
                raise RequestCancellationError(self._snapshot_locked())
            self._mutation_started = True
            self._phase = str(phase)[:128]
            return self._snapshot_locked()

    def begin_irreversible(self, phase: str) -> InflightSnapshot:
        """Cross a non-rollbackable boundary and reject later cancellation."""

        with self._lock:
            if self._cancellation_requested:
                raise RequestCancellationError(self._snapshot_locked())
            self._mutation_started = True
            self._phase = str(phase)[:128]
            self._accepting_cancellation = False
            return self._snapshot_locked()

    def mark_uncertain(self, phase: str = "completion_uncertain") -> InflightSnapshot:
        with self._lock:
            self._uncertain = True
            self._phase = str(phase)[:128]
            return self._snapshot_locked()

    def claim_cancellation_resolution(self) -> tuple[bool, Any]:
        """Permit exactly one caller to perform lease/CAS cancellation work."""

        with self._lock:
            if self._cancellation_resolved:
                return False, copy.deepcopy(self._cancellation_resolution)
            if self._cancellation_resolving:
                return False, None
            self._cancellation_resolving = True
            return True, None

    def claim_cancellation_begin(self) -> bool:
        with self._lock:
            if self._cancellation_begin_claimed:
                return False
            self._cancellation_begin_claimed = True
            return True

    def finish_cancellation_begin(self) -> None:
        self._cancellation_begin_complete.set()

    def wait_cancellation_begin(self, timeout: float | None = None) -> bool:
        return self._cancellation_begin_complete.wait(timeout)

    def finish_cancellation_resolution(self, result: Any) -> Any:
        with self._lock:
            if not self._cancellation_resolved:
                self._cancellation_resolution = copy.deepcopy(result)
            self._cancellation_resolved = True
            self._cancellation_resolving = False
            self._maybe_terminal_locked()
            resolved = copy.deepcopy(self._cancellation_resolution)
        self._cancellation_resolution_complete.set()
        return resolved

    def wait_cancellation_resolution(self, timeout: float | None = None) -> bool:
        """Wait until the single cancellation resolver publishes its result."""

        return self._cancellation_resolution_complete.wait(timeout)

    def cancellation_resolution(self) -> Any:
        with self._lock:
            return copy.deepcopy(self._cancellation_resolution)

    def begin_gui_phase(self, phase: str) -> InflightSnapshot:
        with self._lock:
            self._active_gui_phases += 1
            self._phase = str(phase)[:128]
            return self._snapshot_locked()

    def end_gui_phase(self) -> InflightSnapshot:
        with self._lock:
            if self._active_gui_phases > 0:
                self._active_gui_phases -= 1
            self._maybe_terminal_locked()
            return self._snapshot_locked()

    def finish_handler(self, status: str) -> InflightSnapshot:
        with self._lock:
            self._handler_finished = True
            self._terminal_status = str(status)[:64]
            self._maybe_terminal_locked()
            return self._snapshot_locked()

    def _maybe_terminal_locked(self) -> None:
        if self._handler_finished and self._active_gui_phases == 0:
            if self._cancellation_requested and not self._cancellation_resolved:
                return
            self._accepting_cancellation = False
            self._terminal = True
            if self._cancellation_requested:
                self._terminal_status = "cancelled"
            self._phase = "terminal"


@dataclass
class InflightRequest:
    session_id: str
    request_id: str
    method: str
    token: CancellationToken
    _credentials: tuple[InflightLeaseCredential, ...] = field(
        default_factory=tuple, repr=False
    )
    _touched_credentials: tuple[InflightLeaseCredential, ...] = field(
        default_factory=tuple, repr=False
    )
    lease_affecting: bool = False
    _credential_lock: threading.RLock = field(
        default_factory=threading.RLock, init=False, repr=False, compare=False
    )

    @property
    def credentials(self) -> tuple[InflightLeaseCredential, ...]:
        with self._credential_lock:
            return self._credentials

    def add_credentials(
        self, credentials: Iterable[InflightLeaseCredential]
    ) -> None:
        with self._credential_lock:
            known = {
                (item.lease_id, item.document_session_uuid, item.generation)
                for item in self._credentials
            }
            additions = tuple(
                item
                for item in credentials
                if (item.lease_id, item.document_session_uuid, item.generation)
                not in known
            )
            self._credentials = self._credentials + additions

    @staticmethod
    def _credential_key(item: InflightLeaseCredential) -> tuple[str, str, int]:
        return item.lease_id, item.document_session_uuid, item.generation

    def touch_credentials(
        self, credentials: Iterable[InflightLeaseCredential]
    ) -> None:
        """Record only credentials whose documents this request authorized."""

        with self._credential_lock:
            known = {self._credential_key(item) for item in self._touched_credentials}
            additions = tuple(
                item
                for item in credentials
                if self._credential_key(item) not in known
            )
            self._touched_credentials = self._touched_credentials + additions

    @property
    def affected_credentials(self) -> tuple[InflightLeaseCredential, ...]:
        with self._credential_lock:
            return self._touched_credentials

    def scrub_credentials(self) -> None:
        with self._credential_lock:
            self._credentials = ()
            self._touched_credentials = ()


@dataclass(frozen=True)
class CancellationResult:
    status: str
    request: InflightSnapshot | None

    def to_public_dict(self) -> dict[str, Any]:
        result = {"status": self.status}
        if self.request is not None:
            result["request"] = self.request.to_public_dict()
        return result


class InflightRequestRegistry:
    """Own active request state and bounded redacted terminal tombstones."""

    def __init__(self, *, max_terminal_entries: int = 4096) -> None:
        if max_terminal_entries <= 0:
            raise ValueError("max_terminal_entries must be positive")
        self._max_terminal_entries = int(max_terminal_entries)
        self._active: dict[tuple[str, str], InflightRequest] = {}
        self._terminal: OrderedDict[tuple[str, str], InflightRequest] = OrderedDict()
        self._lock = threading.RLock()

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
        credentials: Iterable[InflightLeaseCredential] = (),
        *,
        lease_affecting: bool = False,
    ) -> InflightRequest:
        key = self._key(session_id, request_id)
        with self._lock:
            if key in self._active or key in self._terminal:
                raise ValueError("authenticated request is already registered")
            request = InflightRequest(
                session_id=key[0],
                request_id=key[1],
                method=str(method),
                token=CancellationToken(key[0], key[1], str(method)),
                lease_affecting=bool(lease_affecting),
                _credentials=tuple(credentials),
            )
            self._active[key] = request
            return request

    def get(self, session_id: str, request_id: str) -> InflightRequest | None:
        key = self._key(session_id, request_id)
        with self._lock:
            return self._active.get(key) or self._terminal.get(key)

    def request_cancel(self, session_id: str, request_id: str) -> CancellationResult:
        key = self._key(session_id, request_id)
        with self._lock:
            request = self._active.get(key)
            if request is None:
                terminal = self._terminal.get(key)
                if terminal is None:
                    # Deliberately indistinguishable from a foreign-session key.
                    return CancellationResult("unknown", None)
                return CancellationResult("completed", terminal.token.snapshot())
            newly_requested, snapshot = request.token.request_cancel()
            if not newly_requested and not snapshot.cancellation_requested:
                return CancellationResult("not_cancellable", snapshot)
            return CancellationResult(
                "requested" if newly_requested else "already_requested", snapshot
            )

    def begin_gui_phase(
        self, session_id: str, request_id: str, phase: str
    ) -> CancellationToken | None:
        key = self._key(session_id, request_id)
        with self._lock:
            request = self._active.get(key)
            if request is None:
                return None
            request.token.begin_gui_phase(phase)
            return request.token

    def end_gui_phase(self, session_id: str, request_id: str) -> InflightSnapshot | None:
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
    ) -> InflightSnapshot | None:
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
        request: InflightRequest,
        snapshot: InflightSnapshot,
    ) -> None:
        if not snapshot.terminal:
            return
        self._active.pop(key, None)
        request.scrub_credentials()
        self._terminal[key] = request
        self._terminal.move_to_end(key)
        while len(self._terminal) > self._max_terminal_entries:
            self._terminal.popitem(last=False)

    def status(self, session_id: str, request_id: str) -> InflightSnapshot | None:
        request = self.get(session_id, request_id)
        return request.token.snapshot() if request is not None else None

    def refresh_terminal(
        self, session_id: str, request_id: str
    ) -> InflightSnapshot | None:
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
        request: InflightRequest,
        result: Any,
    ) -> Any:
        """Publish a cancellation result and atomically retire a terminal request.

        Keeping both operations under the registry lock prevents status readers
        from observing a terminal token in the active registry and guarantees
        that credential scrubbing happens with terminalization.
        """

        key = self._key(request.session_id, request.request_id)
        with self._lock:
            registered = self._active.get(key) or self._terminal.get(key)
            if registered is not request:
                raise ValueError("cancellation request is not registered")
            resolved = request.token.finish_cancellation_resolution(result)
            self._terminalize_locked(key, request, request.token.snapshot())
            return resolved

    def request_cancel_all(self) -> tuple[InflightRequest, ...]:
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
