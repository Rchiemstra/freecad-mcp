"""Signal-driven GUI mutation-readiness continuation contracts."""

from __future__ import annotations

import inspect
import threading
import time
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from addon.FreeCADMCP.dispatch.gui_core import GuiDispatchCore
from addon.FreeCADMCP.dispatch.gui_errors import GuiDispatchTimeout, GuiTaskError
from addon.FreeCADMCP.dispatch.gui_request import GuiDeferDecision
from addon.FreeCADMCP.rpc_server.methods.dispatch_helpers_ops.dispatch_gui import (
    _build_mutation_readiness_probe,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.mutation_readiness import (
    document_readiness,
)
from addon.FreeCADMCP.rpc_server.gui_dispatcher_qt import (
    _DocumentEventMailbox,
    _MutationReadinessObserver,
    _ObserverCleanupController,
    GuiDispatcher,
)
from tests.helpers.native_readiness import ready_native_readiness


class _Harness:
    def __init__(self) -> None:
        self.owner = threading.get_ident()
        self.wakes = 0
        self.events: list[str] = []

    def core(self) -> GuiDispatchCore:
        return GuiDispatchCore(
            is_gui_thread=lambda: threading.get_ident() == self.owner,
            wake_gui=self._wake,
            schedule_wake=lambda _delay, _callback: pytest.fail(
                "readiness continuation must not schedule a polling wake"
            ),
            gui_busy=lambda: False,
            emit_telemetry=lambda _source, event, **_fields: self.events.append(
                event
            ),
        )

    def _wake(self) -> None:
        self.wakes += 1


def _wait_until(predicate, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.001)
    assert predicate()


def _capture(target, results: list[Any], errors: list[BaseException]) -> None:
    try:
        results.append(target())
    except BaseException as exc:
        errors.append(exc)


def _defer_while(state: dict[str, bool], key: str, probes: list[str]):
    def probe():
        probes.append(key)
        if state["blocked"]:
            return GuiDeferDecision((key,), "native_recomputing")
        return None

    return probe


@pytest.mark.unit
def test_observer_uses_only_authoritative_stable_callback_for_resume() -> None:
    stable: list[str] = []
    deleted: list[str] = []
    observer = _MutationReadinessObserver(stable.append, deleted.append)
    document = SimpleNamespace(Name="Model")

    assert not hasattr(observer, "slotRecomputedDocument")
    assert not hasattr(observer, "slotCommitTransaction")
    assert not hasattr(observer, "slotAbortTransaction")

    observer.slotBecameStableDocument(document)
    assert stable == ["Model"]
    assert deleted == []

    observer.slotDeletedDocument(document)
    assert stable == ["Model"]
    assert deleted == ["Model"]


@pytest.mark.unit
def test_document_event_mailbox_has_no_concurrent_producer_drain_loss() -> None:
    mailbox = _DocumentEventMailbox()
    count = 32
    barrier = threading.Barrier(count + 1)
    threads = []

    assert mailbox.publish("stable", "Duplicate") is True
    assert mailbox.publish("stable", "Duplicate") is False
    assert mailbox.take() == (("stable", "Duplicate"),)

    for index in range(count):
        thread = threading.Thread(
            target=lambda item=index: (
                barrier.wait(),
                mailbox.publish("stable", f"Model{item}"),
            )
        )
        thread.start()
        threads.append(thread)

    barrier.wait()
    first = set(mailbox.take())
    for thread in threads:
        thread.join(timeout=1.0)
    second = set(mailbox.take())

    assert first.isdisjoint(second)
    assert first | second == {
        ("stable", f"Model{index}") for index in range(count)
    }
    assert mailbox.take() == ()


def _cleanup_controller(*, remove, delete=None):
    owner_thread = threading.get_ident()
    queued: list[Callable[[], None]] = []
    failures: list[str] = []
    deletions: list[int] = []
    controller = _ObserverCleanupController(
        is_owner=lambda: threading.get_ident() == owner_thread,
        queue_owner=lambda: queued.append(controller.run_on_owner),
        delete_owner=(
            delete
            if delete is not None
            else lambda: deletions.append(threading.get_ident())
        ),
        report_failure=failures.append,
    )
    observer = object()
    controller.bind(
        SimpleNamespace(removeDocumentObserver=remove),
        observer,
    )
    return controller, observer, queued, failures, deletions


@pytest.mark.unit
@pytest.mark.parametrize("delete_after", [False, True])
def test_observer_stop_and_delete_are_marshaled_to_owner_thread(
    delete_after: bool,
) -> None:
    removals: list[tuple[Any, int]] = []
    controller, observer, queued, failures, deletions = _cleanup_controller(
        remove=lambda item: removals.append((item, threading.get_ident()))
    )
    results: list[bool] = []
    worker = threading.Thread(
        target=lambda: results.append(
            controller.request(delete_after=delete_after)
        )
    )
    worker.start()
    worker.join(timeout=1.0)

    assert results == [True]
    assert removals == []
    assert len(queued) == 1
    assert controller.status["cleanup_pending"] is True

    queued.pop()()

    assert removals == [(observer, threading.get_ident())]
    assert failures == []
    assert controller.status["installed"] is False
    assert deletions == ([threading.get_ident()] if delete_after else [])


@pytest.mark.unit
@pytest.mark.parametrize("operation", ["stop", "delete"])
def test_dispatcher_stop_and_delete_delegate_cleanup_off_owner(
    operation: str,
) -> None:
    removals: list[tuple[Any, int]] = []
    controller, observer, queued, failures, deletions = _cleanup_controller(
        remove=lambda item: removals.append((item, threading.get_ident()))
    )
    stopped: list[int] = []
    dispatcher = SimpleNamespace(
        _core=SimpleNamespace(
            stop_accepting=lambda: stopped.append(threading.get_ident())
        ),
        _observer_cleanup=controller,
    )

    callback = (
        GuiDispatcher.stop_accepting
        if operation == "stop"
        else GuiDispatcher.deleteLater
    )
    worker = threading.Thread(target=lambda: callback(dispatcher))
    worker.start()
    worker.join(timeout=1.0)

    assert removals == []
    assert len(queued) == 1
    assert stopped == ([] if operation == "delete" else [worker.ident])

    queued.pop()()

    assert removals == [(observer, threading.get_ident())]
    assert failures == []
    assert deletions == (
        [threading.get_ident()] if operation == "delete" else []
    )


@pytest.mark.unit
def test_observer_removal_failure_retains_refs_and_retries_on_owner() -> None:
    attempts: list[Any] = []
    fail = {"value": True}

    def remove(observer):
        attempts.append(observer)
        if fail["value"]:
            raise RuntimeError("observer registry busy")

    controller, observer, queued, failures, _deletions = _cleanup_controller(
        remove=remove
    )

    assert controller.request() is False
    status = controller.status
    assert status["installed"] is True
    assert status["retryable"] is True
    assert "observer registry busy" in status["last_error"]
    assert failures and "observer registry busy" in failures[-1]
    assert queued == []

    fail["value"] = False
    assert controller.retry() is True
    assert attempts == [observer, observer]
    assert controller.status == {
        "installed": False,
        "cleanup_pending": False,
        "delete_requested": False,
        "delete_scheduled": False,
        "last_error": None,
        "attempt_complete": True,
        "retryable": False,
    }


@pytest.mark.unit
def test_dispatcher_dispose_timeout_retains_queued_cleanup_for_retry() -> None:
    controller, observer, queued, failures, deletions = _cleanup_controller(
        remove=lambda _item: None
    )
    dispatcher = SimpleNamespace(
        _core=SimpleNamespace(stop_accepting=lambda: None),
        _observer_cleanup=controller,
    )
    errors: list[BaseException] = []
    worker = threading.Thread(
        target=lambda: _capture(
            lambda: GuiDispatcher.dispose(dispatcher, 0.02),
            [],
            errors,
        )
    )
    worker.start()
    worker.join(timeout=1.0)

    assert len(errors) == 1 and isinstance(errors[0], TimeoutError)
    assert len(queued) == 1
    assert controller.status["installed"] is True
    assert controller.status["cleanup_pending"] is True
    assert controller.status["attempt_complete"] is False

    # A later owner-thread shutdown must claim the already queued cleanup
    # synchronously instead of blocking its own event loop waiting for it.
    GuiDispatcher.dispose(dispatcher, 0.1)
    controller.wait(0.1)
    queued.pop()()  # The stale queued slot is harmless and idempotent.

    assert controller.status["installed"] is False
    assert failures == []
    assert deletions == [threading.get_ident()]
    assert observer is not None


@pytest.mark.unit
def test_dispatcher_dispose_surfaces_failure_and_retries_retained_observer() -> None:
    fail = {"value": True}
    removals: list[Any] = []

    def remove(observer):
        removals.append(observer)
        if fail["value"]:
            raise RuntimeError("observer registry busy")

    controller, observer, _queued, failures, deletions = _cleanup_controller(
        remove=remove
    )
    dispatcher = SimpleNamespace(
        _core=SimpleNamespace(stop_accepting=lambda: None),
        _observer_cleanup=controller,
    )

    with pytest.raises(RuntimeError, match="observer registry busy"):
        GuiDispatcher.dispose(dispatcher, 0.1)

    assert controller.status["installed"] is True
    assert controller.status["retryable"] is True
    fail["value"] = False

    GuiDispatcher.dispose(dispatcher, 0.1)

    assert removals == [observer, observer]
    assert failures and "observer registry busy" in failures[-1]
    assert deletions == [threading.get_ident()]


@pytest.mark.unit
def test_terminal_disposal_retry_never_touches_deleted_qobject_api() -> None:
    controller, _observer, _queued, _failures, _deletions = _cleanup_controller(
        remove=lambda _item: None
    )
    assert controller.request(delete_after=True) is True
    assert controller.disposal_complete is True
    stops: list[bool] = []
    dispatcher = SimpleNamespace(
        _core=SimpleNamespace(stop_accepting=lambda: stops.append(True)),
        _observer_cleanup=controller,
        _owner_thread_ident=threading.get_ident(),
        thread=lambda: pytest.fail("deleted QObject API must not be touched"),
    )
    dispatcher.dispose = lambda timeout: GuiDispatcher.dispose(
        dispatcher,
        timeout,
    )

    assert GuiDispatcher.dispose_on_owner_thread(dispatcher, 0.1) is True
    assert stops == [True]


@pytest.mark.unit
@pytest.mark.parametrize("field", ["recomputing", "notification_replay", "commit_barrier"])
def test_dispatch_boundary_probe_defers_only_async_native_state(field: str) -> None:
    native = ready_native_readiness()
    native.update(ready=False, **{field: True})
    document = SimpleNamespace(
        Name="Model",
        getMutationReadiness=lambda: dict(native),
    )
    collaborators = SimpleNamespace(
        freecad=SimpleNamespace(
            getDocument=lambda name: document if name == "Model" else None
        )
    )
    phases: list[str] = []
    inflight = SimpleNamespace(
        token=SimpleNamespace(checkpoint=lambda phase: phases.append(phase))
    )
    probe = _build_mutation_readiness_probe(
        collaborators,
        {"doc_names": ("Model",)},
        inflight,
    )

    decision = probe()

    assert decision is not None
    assert decision.document_keys == ("Model",)
    assert phases == ["gui_mutation_readiness_probe"]

    native.update(ready=True, recomputing=False, notification_replay=False, commit_barrier=False)
    assert probe() is None


@pytest.mark.unit
def test_stable_callback_observes_authoritatively_ready_document() -> None:
    native = ready_native_readiness()
    native.update(ready=False, recomputing=True)
    document = SimpleNamespace(
        Name="Model",
        getMutationReadiness=lambda: dict(native),
    )
    collaborators = SimpleNamespace(
        freecad=SimpleNamespace(getDocument=lambda _name: document)
    )
    probe = _build_mutation_readiness_probe(
        collaborators,
        {"doc_names": ("Model",)},
        inflight=None,
    )
    observed: list[tuple[bool, Any]] = []
    observer = _MutationReadinessObserver(
        lambda _name: observed.append(
            (document_readiness(document)["ready"], probe())
        ),
        lambda _name: None,
    )

    assert probe() is not None
    native.update(ready=True, recomputing=False)
    observer.slotBecameStableDocument(document)

    assert observed == [(True, None)]


@pytest.mark.unit
@pytest.mark.parametrize("marker", [None, False])
def test_probe_never_defers_without_authoritative_stable_event_marker(
    marker: bool | None,
) -> None:
    native = ready_native_readiness()
    native.update(ready=False, recomputing=True)
    if marker is None:
        native.pop("stable_event_supported")
    else:
        native["stable_event_supported"] = marker
    document = SimpleNamespace(
        Name="Model",
        getMutationReadiness=lambda: dict(native),
    )
    collaborators = SimpleNamespace(
        freecad=SimpleNamespace(getDocument=lambda _name: document)
    )
    probe = _build_mutation_readiness_probe(
        collaborators,
        {"doc_names": ("Model",)},
        inflight=None,
    )

    readiness = document_readiness(document)

    assert probe() is None
    assert readiness["ready"] is False
    assert readiness["runtime_compatible"] is False
    assert readiness["stable_event_supported"] is False


@pytest.mark.unit
def test_async_clear_requeues_same_logical_request_exactly_once() -> None:
    harness = _Harness()
    core = harness.core()
    state = {"blocked": True}
    probes: list[str] = []
    executions: list[str] = []
    completions: list[tuple[str, bool]] = []
    results: list[Any] = []
    errors: list[BaseException] = []
    submitter = threading.Thread(
        target=_capture,
        args=(
            lambda: core.submit(
                lambda: executions.append("request") or 17,
                1.0,
                request_id="same-request",
                session_id="session",
                document_keys=("Model",),
                defer_probe=_defer_while(state, "Model", probes),
                on_complete=lambda request_id, outcome: completions.append(
                    (request_id, outcome.ok)
                ),
            ),
            results,
            errors,
        ),
    )
    submitter.start()
    _wait_until(lambda: core.pending_count == 1)
    request = core._requests[0]
    deadline = request.deadline_at
    assert deadline is not None

    core.drain_one()
    assert core.deferred_count == 1
    assert core._deferred_requests[0] is request
    assert request.deadline_at == deadline
    assert executions == []
    assert submitter.is_alive()

    state["blocked"] = False
    core.notify_document_readiness_changed("Model")
    core.notify_document_readiness_changed("Model")
    assert core._requests[0] is request
    assert request.deadline_at == deadline
    core.drain_one()
    submitter.join(timeout=1.0)

    assert results == [17]
    assert errors == []
    assert probes == ["Model", "Model"]
    assert executions == ["request"]
    assert completions == [("same-request", True)]
    assert harness.events.count("gui_execution_deferred") == 1
    assert harness.events.count("gui_execution_requeued") == 1
    assert harness.events.count("gui_execution_started") == 1
    assert harness.events.count("gui_execution_completed") == 1


@pytest.mark.unit
def test_native_signal_during_probe_is_not_lost_before_defer_registration() -> None:
    harness = _Harness()
    core = harness.core()
    blocked = {"value": True}
    owner_slots: list[Callable[[], None]] = []
    executions: list[str] = []
    completions: list[str] = []
    results: list[Any] = []
    errors: list[BaseException] = []

    def probe():
        if not blocked["value"]:
            return None
        # Model a native state transition racing the first readiness snapshot.
        # The Qt bridge always queues its owner-thread slot, so the stale
        # decision is registered before this callback can promote it.
        blocked["value"] = False
        owner_slots.append(
            lambda: core.notify_document_readiness_changed("Model")
        )
        return GuiDeferDecision(("Model",), "native_recomputing")

    submitter = threading.Thread(
        target=_capture,
        args=(
            lambda: core.submit(
                lambda: executions.append("ran") or 23,
                1.0,
                request_id="race-request",
                session_id="race-session",
                document_keys=("Model",),
                defer_probe=probe,
                on_complete=lambda request_id, _outcome: completions.append(
                    request_id
                ),
            ),
            results,
            errors,
        ),
    )
    submitter.start()
    _wait_until(lambda: core.pending_count == 1)

    core.drain_one()
    assert core.deferred_count == 1
    assert len(owner_slots) == 1

    owner_slots.pop()()
    core.drain_one()
    submitter.join(timeout=1.0)

    assert results == [23]
    assert errors == []
    assert executions == ["ran"]
    assert completions == ["race-request"]
    assert core.pending_count == 0


@pytest.mark.unit
def test_deferred_request_cancellation_is_final_and_exactly_once() -> None:
    harness = _Harness()
    core = harness.core()
    state = {"blocked": True}
    executions: list[bool] = []
    completions: list[bool] = []
    errors: list[BaseException] = []
    submitter = threading.Thread(
        target=_capture,
        args=(
            lambda: core.submit(
                lambda: executions.append(True),
                1.0,
                request_id="cancel-me",
                session_id="session",
                document_keys=("Model",),
                defer_probe=_defer_while(state, "Model", []),
                on_complete=lambda _request_id, outcome: completions.append(
                    outcome.ok
                ),
            ),
            [],
            errors,
        ),
    )
    submitter.start()
    _wait_until(lambda: core.pending_count == 1)
    core.drain_one()
    assert core.deferred_count == 1

    assert core.cancel_request("session", "cancel-me") == "cancelled_pending"
    submitter.join(timeout=1.0)
    state["blocked"] = False
    core.notify_document_readiness_changed("Model")
    core.drain_one()

    assert executions == []
    assert len(errors) == 1 and isinstance(errors[0], GuiTaskError)
    assert completions == [False]
    assert core.pending_count == 0


@pytest.mark.unit
def test_stop_accepting_cleans_deferred_request_and_releases_waiter() -> None:
    harness = _Harness()
    core = harness.core()
    state = {"blocked": True}
    executions: list[bool] = []
    completions: list[bool] = []
    errors: list[BaseException] = []
    submitter = threading.Thread(
        target=_capture,
        args=(
            lambda: core.submit(
                lambda: executions.append(True),
                1.0,
                document_keys=("Model",),
                defer_probe=_defer_while(state, "Model", []),
                on_complete=lambda _request_id, outcome: completions.append(
                    outcome.ok
                ),
            ),
            [],
            errors,
        ),
    )
    submitter.start()
    _wait_until(lambda: core.pending_count == 1)
    core.drain_one()

    core.stop_accepting()
    submitter.join(timeout=1.0)
    state["blocked"] = False
    core.notify_document_readiness_changed("Model")
    core.drain_one()

    assert executions == []
    assert len(errors) == 1 and isinstance(errors[0], GuiTaskError)
    assert completions == [False]
    assert core.pending_count == 0
    assert core.deferred_count == 0


@pytest.mark.unit
def test_document_deletion_cancels_instead_of_resuming_deferred_work() -> None:
    harness = _Harness()
    core = harness.core()
    executions: list[bool] = []
    errors: list[BaseException] = []
    submitter = threading.Thread(
        target=_capture,
        args=(
            lambda: core.submit(
                lambda: executions.append(True),
                1.0,
                document_keys=("Model",),
                defer_probe=lambda: GuiDeferDecision(
                    ("Model",), "native_recomputing"
                ),
            ),
            [],
            errors,
        ),
    )
    submitter.start()
    _wait_until(lambda: core.pending_count == 1)
    core.drain_one()

    core.notify_document_deleted("Model")
    submitter.join(timeout=1.0)
    core.notify_document_readiness_changed("Model")
    core.drain_one()

    assert executions == []
    assert len(errors) == 1 and isinstance(errors[0], GuiTaskError)
    assert core.pending_count == 0
    assert core.deferred_count == 0


@pytest.mark.unit
def test_deferred_request_timeout_completes_before_execution() -> None:
    harness = _Harness()
    core = harness.core()
    state = {"blocked": True}
    executions: list[bool] = []
    completions: list[bool] = []
    errors: list[BaseException] = []
    submitter = threading.Thread(
        target=_capture,
        args=(
            lambda: core.submit(
                lambda: executions.append(True),
                0.03,
                request_id="times-out",
                session_id="session",
                document_keys=("Model",),
                defer_probe=_defer_while(state, "Model", []),
                on_complete=lambda _request_id, outcome: completions.append(
                    outcome.ok
                ),
            ),
            [],
            errors,
        ),
    )
    submitter.start()
    _wait_until(lambda: core.pending_count == 1)
    core.drain_one()
    submitter.join(timeout=1.0)

    assert len(errors) == 1 and isinstance(errors[0], GuiDispatchTimeout)
    assert errors[0].error_code == "GUI_TIMEOUT_BEFORE_EXECUTION"
    assert executions == []
    assert completions == [False]
    assert core.pending_count == 0

    state["blocked"] = False
    core.notify_document_readiness_changed("Model")
    core.drain_one()
    assert executions == []
    assert completions == [False]


@pytest.mark.unit
def test_expired_retained_deadline_wins_signal_requeue_race() -> None:
    harness = _Harness()
    core = harness.core()
    state = {"blocked": True}
    executions: list[bool] = []
    errors: list[BaseException] = []
    submitter = threading.Thread(
        target=_capture,
        args=(
            lambda: core.submit(
                lambda: executions.append(True),
                1.0,
                document_keys=("Model",),
                defer_probe=_defer_while(state, "Model", []),
            ),
            [],
            errors,
        ),
    )
    submitter.start()
    _wait_until(lambda: core.pending_count == 1)
    core.drain_one()
    request = core._deferred_requests[0]
    request.deadline_at = 0.0

    state["blocked"] = False
    core.notify_document_readiness_changed("Model")
    core.drain_one()
    submitter.join(timeout=1.0)

    assert len(errors) == 1 and isinstance(errors[0], GuiDispatchTimeout)
    assert errors[0].error_code == "GUI_TIMEOUT_BEFORE_EXECUTION"
    assert executions == []
    assert core.pending_count == 0


@pytest.mark.unit
def test_unrelated_document_runs_while_deferred_and_cannot_wake_it() -> None:
    harness = _Harness()
    core = harness.core()
    state = {"blocked": True}
    execution: list[str] = []
    first_results: list[Any] = []
    first_errors: list[BaseException] = []
    first = threading.Thread(
        target=_capture,
        args=(
            lambda: core.submit(
                lambda: execution.append("A1") or "A1",
                1.0,
                document_keys=("A",),
                defer_probe=_defer_while(state, "A", []),
            ),
            first_results,
            first_errors,
        ),
    )
    first.start()
    _wait_until(lambda: core.pending_count == 1)
    core.drain_one()

    second_results: list[Any] = []
    second_errors: list[BaseException] = []
    second = threading.Thread(
        target=_capture,
        args=(
            lambda: core.submit(
                lambda: execution.append("B") or "B",
                1.0,
                document_keys=("B",),
            ),
            second_results,
            second_errors,
        ),
    )
    second.start()
    _wait_until(lambda: core.pending_count == 2)
    core.drain_one()
    second.join(timeout=1.0)

    core.notify_document_readiness_changed("B")
    core.drain_one()
    assert execution == ["B"]
    assert first.is_alive()
    assert core.deferred_count == 1

    state["blocked"] = False
    core.notify_document_readiness_changed("A")
    core.drain_one()
    first.join(timeout=1.0)

    assert execution == ["B", "A1"]
    assert first_results == ["A1"] and first_errors == []
    assert second_results == ["B"] and second_errors == []


@pytest.mark.unit
def test_later_same_document_request_cannot_overtake_deferred_request() -> None:
    harness = _Harness()
    core = harness.core()
    state = {"blocked": True}
    execution: list[str] = []
    threads: list[threading.Thread] = []
    errors: list[BaseException] = []

    for name, probe in (
        ("first", _defer_while(state, "Model", [])),
        ("second", None),
    ):
        thread = threading.Thread(
            target=_capture,
            args=(
                lambda item=name, gate=probe: core.submit(
                    lambda: execution.append(item) or item,
                    1.0,
                    document_keys=("Model",),
                    defer_probe=gate,
                ),
                [],
                errors,
            ),
        )
        thread.start()
        threads.append(thread)
        _wait_until(lambda expected=len(threads): core.pending_count == expected)
        if name == "first":
            core.drain_one()

    core.drain_one()
    assert execution == []
    state["blocked"] = False
    core.notify_document_readiness_changed("Model")
    core.drain_one()
    core.drain_one()
    for thread in threads:
        thread.join(timeout=1.0)

    assert execution == ["first", "second"]
    assert errors == []


@pytest.mark.unit
def test_readiness_continuation_contains_no_event_pump_or_poll_loop() -> None:
    from addon.FreeCADMCP.dispatch import gui_core
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import (
        mutation_readiness_wait,
    )

    sources = (
        inspect.getsource(gui_core.GuiDispatchCore._defer_for_readiness),
        inspect.getsource(gui_core.GuiDispatchCore.notify_document_readiness_changed),
        inspect.getsource(mutation_readiness_wait),
    )
    combined = "\n".join(sources)
    assert "processEvents" not in combined
    assert "sleep(" not in combined
    assert "schedule_wake" not in sources[0]

    qt_adapter = Path(
        "addon/FreeCADMCP/rpc_server/gui_dispatcher_qt.py"
    ).read_text(encoding="utf-8")
    readiness_bridge = qt_adapter.split(
        "class _MutationReadinessObserver:", 1
    )[1].split("class GuiDispatcher", 1)[0]
    readiness_slot = qt_adapter.split(
        "def _native_document_event", 1
    )[1].split("def _run_observer_cleanup", 1)[0]
    dispatcher_init = inspect.getsource(GuiDispatcher.__init__)
    assert (
        "self.native_document_event.connect(self._native_document_event, queued)"
        in dispatcher_init
    )
    assert "QTimer" not in readiness_bridge + readiness_slot
    assert "processEvents" not in readiness_bridge + readiness_slot
