"""Qt ownership adapter for the standard-library GUI dispatch core."""

from __future__ import annotations

import threading
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from PySide import QtCore

try:  # Installed add-on package.
    from ..dispatch.gui_core import GuiDispatchCore
    from ..dispatch.gui_outcome import GuiOutcome
    from ..dispatch.gui_request import DeferProbe as _DeferProbe
except ImportError:  # Flat FreeCAD add-on import (``import rpc_server``).
    from dispatch.gui_core import GuiDispatchCore
    from dispatch.gui_outcome import GuiOutcome
    from dispatch.gui_request import DeferProbe as _DeferProbe
from .gui_dispatcher_ops.navigation_guards import gui_busy_for_3d_navigation
from .telemetry import emit as emit_telemetry

__all__ = ["GuiDispatcher"]


class _MutationReadinessObserver:
    """Bridge native stable/deleted document events into queued Qt signals."""

    def __init__(
        self,
        notify_stable: Callable[[str], None],
        notify_deleted: Callable[[str], None],
    ) -> None:
        self._notify_stable = notify_stable
        self._notify_deleted = notify_deleted

    @staticmethod
    def _document_name(document: Any) -> str:
        return str(getattr(document, "Name", "") or "")

    def slotBecameStableDocument(self, document: Any) -> None:
        """Resume only at the native lane's authoritative stable boundary."""

        name = self._document_name(document)
        if name:
            self._notify_stable(name)

    def slotDeletedDocument(self, document: Any) -> None:
        """Cancel queued work for a document that no longer exists."""

        name = self._document_name(document)
        if name:
            self._notify_deleted(name)


class _DocumentEventMailbox:
    """Coalesce cross-thread native events with an atomic set-and-swap."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: set[tuple[str, str]] = set()

    def publish(self, kind: str, document_key: str) -> bool:
        event = (str(kind), str(document_key))
        with self._lock:
            if event in self._pending:
                return False
            self._pending.add(event)
            return True

    def take(self) -> tuple[tuple[str, str], ...]:
        with self._lock:
            pending = self._pending
            self._pending = set()
        return tuple(sorted(pending))


class _ObserverCleanupController:
    """Marshal observer removal to its owner and retain failed registrations."""

    def __init__(
        self,
        *,
        is_owner: Callable[[], bool],
        queue_owner: Callable[[], None],
        delete_owner: Callable[[], None],
        report_failure: Callable[[str], None],
    ) -> None:
        self._is_owner = is_owner
        self._queue_owner = queue_owner
        self._delete_owner = delete_owner
        self._report_failure = report_failure
        self._lock = threading.RLock()
        self._freecad: Any | None = None
        self._observer: Any | None = None
        self._pending = False
        self._delete_requested = False
        self._delete_scheduled = False
        self._last_error: str | None = None
        self._completion = threading.Event()

    def bind(self, freecad: Any, observer: Any) -> None:
        with self._lock:
            if self._observer is not None:
                raise RuntimeError("readiness observer is already registered")
            self._freecad = freecad
            self._observer = observer
            self._last_error = None

    @property
    def supports_continuations(self) -> bool:
        with self._lock:
            return (
                self._observer is not None
                and not self._pending
                and self._last_error is None
            )

    @property
    def disposal_complete(self) -> bool:
        """Return whether deletion was safely scheduled and no Qt work remains."""

        with self._lock:
            return bool(
                self._observer is None
                and not self._pending
                and self._last_error is None
                and self._delete_scheduled
                and self._completion.is_set()
            )

    @property
    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "installed": self._observer is not None,
                "cleanup_pending": self._pending,
                "delete_requested": self._delete_requested,
                "delete_scheduled": self._delete_scheduled,
                "last_error": self._last_error,
                "attempt_complete": self._completion.is_set(),
                "retryable": self._last_error is not None
                and (
                    self._observer is not None
                    or (
                        self._delete_requested
                        and not self._delete_scheduled
                    )
                ),
            }

    def _record_failure(self, message: str) -> None:
        with self._lock:
            self._pending = False
            self._last_error = str(message)
            self._completion.set()
        with suppress(Exception):
            self._report_failure(str(message))

    def request(self, *, delete_after: bool = False) -> bool:
        with self._lock:
            self._delete_requested = self._delete_requested or delete_after
            if self._delete_scheduled:
                return True
            already_pending = self._pending
            if not already_pending:
                self._pending = True
                self._completion.clear()
        try:
            on_owner = bool(self._is_owner())
        except Exception as exc:
            self._record_failure(f"could not inspect QObject ownership: {exc}")
            return False
        if on_owner:
            return self.run_on_owner()
        if already_pending:
            return True
        try:
            self._queue_owner()
            return True
        except Exception as exc:
            self._record_failure(f"could not queue observer cleanup: {exc}")
            return False

    def run_on_owner(self) -> bool:
        try:
            if not self._is_owner():
                self._record_failure(
                    "readiness observer cleanup ran off the QObject owner thread"
                )
                return False
        except Exception as exc:
            self._record_failure(f"could not inspect QObject ownership: {exc}")
            return False

        with self._lock:
            self._pending = False
            freecad = self._freecad
            observer = self._observer
        if observer is not None:
            remove_observer = getattr(freecad, "removeDocumentObserver", None)
            if not callable(remove_observer):
                self._record_failure(
                    "FreeCAD.removeDocumentObserver is unavailable"
                )
                return False
            try:
                remove_observer(observer)
            except Exception as exc:
                self._record_failure(f"could not remove readiness observer: {exc}")
                return False

        with self._lock:
            self._freecad = None
            self._observer = None
            self._last_error = None
            delete_now = self._delete_requested and not self._delete_scheduled
            if delete_now:
                self._delete_scheduled = True
        if not delete_now:
            self._completion.set()
            return True
        try:
            self._delete_owner()
            self._completion.set()
            return True
        except Exception as exc:
            with self._lock:
                self._delete_scheduled = False
            self._record_failure(f"could not queue QObject deletion: {exc}")
            return False

    def retry(self) -> bool:
        with self._lock:
            if self._last_error is None and not self._pending:
                return True
        return self.request()

    def wait(self, timeout: float) -> None:
        """Wait for one cleanup attempt and raise unless it completed safely."""

        if not self._completion.wait(timeout):
            raise TimeoutError(
                "readiness observer cleanup did not complete within "
                f"{timeout:.3f} seconds"
            )
        with self._lock:
            error = self._last_error
            pending = self._pending
            observer_retained = self._observer is not None
            deletion_incomplete = (
                self._delete_requested and not self._delete_scheduled
            )
        if error is not None:
            raise RuntimeError(error)
        if pending or observer_retained or deletion_incomplete:
            raise RuntimeError(
                "readiness observer cleanup reported incomplete state"
            )


class GuiDispatcher(QtCore.QObject):
    """Bind Qt thread ownership and queued wakeups to ``GuiDispatchCore``."""

    wake_requested = QtCore.Signal()
    native_document_event = QtCore.Signal()
    observer_cleanup_requested = QtCore.Signal()

    def __init__(self, parent: QtCore.QObject | None = None):
        super().__init__(parent)
        self._owner_thread_ident = threading.get_ident()
        self._core = GuiDispatchCore(
            is_gui_thread=lambda: QtCore.QThread.currentThread() == self.thread(),
            wake_gui=self.wake_requested.emit,
            schedule_wake=lambda delay_ms, callback: QtCore.QTimer.singleShot(
                delay_ms,
                callback,
            ),
            gui_busy=gui_busy_for_3d_navigation,
            emit_telemetry=emit_telemetry,
        )
        try:
            queued = QtCore.Qt.ConnectionType.QueuedConnection
        except AttributeError:
            queued = QtCore.Qt.QueuedConnection
        self.wake_requested.connect(self._drain_one, queued)
        self.native_document_event.connect(self._native_document_event, queued)
        self._document_events = _DocumentEventMailbox()
        self._observer_cleanup = _ObserverCleanupController(
            is_owner=lambda: QtCore.QThread.currentThread() == self.thread(),
            queue_owner=self.observer_cleanup_requested.emit,
            delete_owner=self._delete_on_owner,
            report_failure=self._report_observer_cleanup_failure,
        )
        self.observer_cleanup_requested.connect(
            self._run_observer_cleanup,
            queued,
        )
        self._install_readiness_observer()

    def _install_readiness_observer(self) -> None:
        try:
            import FreeCAD

            add_observer = getattr(FreeCAD, "addDocumentObserver", None)
            if not callable(add_observer):
                return
            observer = _MutationReadinessObserver(
                self._queue_stable_document,
                self._queue_deleted_document,
            )
            add_observer(observer)
            self._observer_cleanup.bind(FreeCAD, observer)
        except Exception:
            # Stock/unit environments without the authoritative stable slot
            # retain the nondeferred dispatcher contract.
            return

    def _queue_document_event(self, kind: str, document_key: str) -> None:
        if self._document_events.publish(kind, document_key):
            self.native_document_event.emit()

    def _queue_stable_document(self, document_key: str) -> None:
        self._queue_document_event("stable", document_key)

    def _queue_deleted_document(self, document_key: str) -> None:
        self._queue_document_event("deleted", document_key)

    def _report_observer_cleanup_failure(self, message: str) -> None:
        emit_telemetry(
            "gui_dispatcher",
            "readiness_observer_cleanup_failed",
            status="failed",
            error_code="READINESS_OBSERVER_CLEANUP_FAILED",
            payload={"message": str(message)},
        )

    def _delete_on_owner(self) -> None:
        super().deleteLater()

    def submit(
        self,
        callable_: Callable[[], Any],
        timeout: float | None,
        *,
        request_id: str | None = None,
        session_id: str | None = None,
        on_complete: Callable[[str, GuiOutcome], None] | None = None,
        defer_probe: _DeferProbe | None = None,
        document_keys: tuple[str, ...] = (),
    ) -> Any:
        return self._core.submit(
            callable_,
            timeout,
            request_id=request_id,
            session_id=session_id,
            on_complete=on_complete,
            defer_probe=defer_probe,
            document_keys=document_keys,
        )

    def cancel_request(self, session_id: str, request_id: str) -> str:
        return self._core.cancel_request(session_id, request_id)

    @QtCore.Slot()
    def _drain_one(self) -> None:
        self._core.drain_one()

    @QtCore.Slot()
    def _native_document_event(self) -> None:
        for kind, document_key in self._document_events.take():
            if kind == "stable":
                self._core.notify_document_readiness_changed(document_key)
            elif kind == "deleted":
                self._core.notify_document_deleted(document_key)

    @QtCore.Slot()
    def _run_observer_cleanup(self) -> None:
        self._observer_cleanup.run_on_owner()

    def stop_accepting(self) -> None:
        self._core.stop_accepting()
        self._observer_cleanup.request()

    def deleteLater(self) -> None:
        self._observer_cleanup.request(delete_after=True)

    def dispose(self, timeout: float = 2.0) -> None:
        """Synchronously stop and release this dispatcher within *timeout*."""

        bounded_timeout = float(timeout)
        if not 0.0 < bounded_timeout < float("inf"):
            raise ValueError("dispatcher disposal timeout must be finite and positive")
        self._core.stop_accepting()
        self._observer_cleanup.request(delete_after=True)
        self._observer_cleanup.wait(bounded_timeout)

    def dispose_on_owner_thread(self, timeout: float = 2.0) -> bool:
        """Dispose synchronously when shutdown is running on the Qt owner."""

        # Once deleteLater has run, touching QObject APIs such as thread()
        # may raise because the C++ wrapper is already gone. The controller's
        # terminal state is pure Python and makes a retained-resource retry
        # safe from any caller.
        if self._observer_cleanup.disposal_complete:
            self.dispose(timeout)
            return True
        if threading.get_ident() != self._owner_thread_ident:
            return False
        self.dispose(timeout)
        return True

    def retry_readiness_observer_cleanup(self) -> bool:
        return self._observer_cleanup.retry()

    @property
    def pending_count(self) -> int:
        return self._core.pending_count

    @property
    def deferred_count(self) -> int:
        return self._core.deferred_count

    @property
    def supports_readiness_continuations(self) -> bool:
        return self._observer_cleanup.supports_continuations

    @property
    def readiness_observer_cleanup_status(self) -> dict[str, Any]:
        return self._observer_cleanup.status
