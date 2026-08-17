"""Focused readiness, quarantine lifecycle, and admission-gate contracts."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from addon.FreeCADMCP import automation_pause
from addon.FreeCADMCP.part3_collaboration.history_head import capture_undo_head
from addon.FreeCADMCP.part3_collaboration.operation_terminal_store import (
    clear_operation_terminal_store,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import mutation_readiness
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_mutation import (
    run_cad_mutation,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.mutation_readiness_wait import (
    asynchronous_transient_document_keys,
    await_transient_mutation_readiness,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.recompute_helpers import (
    recompute_and_wait_gui,
    undo_gui,
)

pytestmark = pytest.mark.unit


def _native_payload(**overrides):
    payload = {
        "ready": True,
        "stable_event_supported": True,
        "pending_transaction": False,
        "booked_transaction": 0,
        "transaction_locked": False,
        "recomputing": False,
        "must_execute": False,
        "pending_removal": False,
        "commit_barrier": False,
        "notification_replay": False,
        "poisoned": False,
        "quarantined": False,
        "diagnostic": "Ready for mutation",
    }
    payload.update(overrides)
    return payload


class _Document:
    def __init__(self, name="Model", uid="uid-1", readiness=None):
        self.Name = name
        self.Uid = uid
        self._readiness = _native_payload(**(readiness or {}))
        self.recompute_calls = 0

    def getMutationReadiness(self):
        return dict(self._readiness)

    def recompute(self):
        self.recompute_calls += 1
        self._readiness = _native_payload()


@pytest.fixture(autouse=True)
def _reset_readiness_state():
    mutation_readiness._QUARANTINED.clear()
    automation_pause._paused = False
    automation_pause._active.clear()
    automation_pause._last_finished = None
    yield
    mutation_readiness._QUARANTINED.clear()
    automation_pause._paused = False
    automation_pause._active.clear()
    automation_pause._last_finished = None


def test_native_not_ready_and_recomputing_are_authoritative_stable_blockers():
    document = _Document(
        readiness={"ready": False, "recomputing": True, "must_execute": True}
    )

    readiness = mutation_readiness.document_readiness(document)

    assert readiness["ready"] is False
    assert readiness["recomputing"] is True
    assert readiness["reasons"] == [
        "native_recomputing",
        "pending_recompute",
        "native_not_ready",
    ]


@pytest.mark.parametrize(
    ("native_outcome", "diagnostic_fragment"),
    [
        (RuntimeError("native getter failed"), "RuntimeError: native getter failed"),
        (["not", "a", "mapping"], "returned list; expected a mapping"),
        ({"ready": True}, "missing"),
        (_native_payload(ready="yes"), "invalid ready"),
        (
            _native_payload(stable_event_supported=False),
            "stable_event_supported must be true",
        ),
        (
            _native_payload(ready=True, notification_replay=True),
            "ready contradicts",
        ),
    ],
)
def test_advertised_native_readiness_failure_is_incompatible_and_fail_closed(
    native_outcome,
    diagnostic_fragment,
):
    class BrokenDocument(_Document):
        def getMutationReadiness(self):
            if isinstance(native_outcome, Exception):
                raise native_outcome
            return native_outcome

        # These legacy probes deliberately describe a clean document.  They
        # must not replace an advertised but unreadable native snapshot.
        @staticmethod
        def hasPendingTransaction():
            return False

        @staticmethod
        def getBookedTransactionID():
            return 0

        @staticmethod
        def isTransactionLocked():
            return False

        @staticmethod
        def mustExecute():
            return False

    readiness = mutation_readiness.document_readiness(BrokenDocument())

    assert readiness["ready"] is False
    assert readiness["reasons"] == ["native_readiness_unavailable"]
    assert readiness["native_readiness_available"] is False
    assert readiness["runtime_compatible"] is False
    assert diagnostic_fragment in readiness["diagnostic"]
    assert readiness["pending_transaction"] is None


def test_malformed_native_readiness_blocks_admission_before_native_commit():
    document = _Document()
    document._readiness = {"ready": True}
    commits = []

    collaborators = SimpleNamespace(
        freecad=SimpleNamespace(getDocument=lambda _name: document),
        commit_compatibility_mutation=lambda *_args, **_kwargs: commits.append(True),
        validate_document_invariants=lambda _document: None,
    )

    result = run_cad_mutation(collaborators, "Model", lambda: True)

    assert result["error_code"] == "MUTATION_NOT_READY"
    assert result["mutation_readiness"][0]["reasons"] == [
        "native_readiness_unavailable"
    ]
    assert result["retryable"] is False
    assert commits == []


def test_public_readiness_snapshot_is_dispatched_to_the_gui_thread():
    document = _Document()
    gui_calls: list[str] = []
    freecad = SimpleNamespace(
        listDocuments=lambda: {document.Name: document},
        getDocument=lambda name: document if name == document.Name else None,
    )
    rpc = SimpleNamespace(
        _cad_collaborators=SimpleNamespace(freecad=freecad),
        _dispatch_gui=lambda callback: (gui_calls.append("dispatch"), callback())[1],
    )

    result = mutation_readiness.get_mutation_readiness(rpc, document.Name)

    assert gui_calls == ["dispatch"]
    assert result["success"] is True
    assert result["ready"] is True


@pytest.mark.parametrize("getter_value", [None, 42])
def test_public_readiness_explains_missing_required_native_getter(getter_value):
    document = SimpleNamespace(Name="LegacyModel", getMutationReadiness=getter_value)
    freecad = SimpleNamespace(
        listDocuments=lambda: {document.Name: document},
        getDocument=lambda name: document if name == document.Name else None,
    )
    rpc = SimpleNamespace(
        _cad_collaborators=SimpleNamespace(freecad=freecad),
        _dispatch_gui=lambda callback: callback(),
    )

    result = mutation_readiness.get_mutation_readiness(rpc, document.Name)

    assert result["success"] is True
    assert result["ready"] is False
    assert result["reasons"] == ["native_readiness_unavailable"]
    assert result["documents"][0]["runtime_compatible"] is False
    assert (
        "does not provide callable getMutationReadiness"
        in result["documents"][0]["diagnostic"]
    )


def test_quarantine_is_bound_to_live_document_lifecycle_not_reused_name():
    closed_document = _Document("Model", "persistent-uid")
    reopened_document = _Document("Model", "persistent-uid")
    mutation_readiness.mark_quarantined(closed_document, "rollback failed")

    assert mutation_readiness.document_readiness(closed_document)["quarantined"] is True
    assert (
        mutation_readiness.document_readiness(reopened_document)["quarantined"] is False
    )

    mutation_readiness.prune_closed_quarantines([reopened_document])
    assert not mutation_readiness._QUARANTINED

    mutation_readiness.mark_quarantined(reopened_document, "rollback failed")
    mutation_readiness.clear_quarantine(reopened_document)
    assert (
        mutation_readiness.document_readiness(reopened_document)["quarantined"] is False
    )


def test_pending_recompute_uses_one_synchronous_settle_with_cancellation_checkpoints():
    document = _Document(readiness={"ready": False, "must_execute": True})
    phases: list[str] = []
    inflight = SimpleNamespace(
        token=SimpleNamespace(checkpoint=lambda phase: phases.append(phase))
    )

    readiness, waited = await_transient_mutation_readiness(
        [document], inflight=inflight
    )

    assert waited is True
    assert document.recompute_calls == 1
    assert readiness[0]["ready"] is True
    assert phases == [
        "mutation_readiness_wait_before",
        "mutation_readiness_wait_after",
    ]


def test_pending_removal_is_authoritative_and_settles_for_deferred_policy():
    document = _Document(readiness={"ready": False, "pending_removal": True})

    before = mutation_readiness.document_readiness(document)
    readiness, waited = await_transient_mutation_readiness(
        [document], allow_pending_recompute=True
    )

    assert before["pending_removal"] is True
    assert before["reasons"] == ["pending_object_removal", "native_not_ready"]
    assert waited is True
    assert document.recompute_calls == 1
    assert readiness[0]["ready"] is True


def test_recomputing_pending_removal_defers_to_the_same_stable_event_request():
    document = _Document(
        readiness={
            "ready": False,
            "recomputing": True,
            "pending_removal": True,
        }
    )

    readiness, waited = await_transient_mutation_readiness(
        [document], allow_pending_recompute=True
    )

    assert waited is False
    assert document.recompute_calls == 0
    assert asynchronous_transient_document_keys(
        readiness, allow_pending_recompute=True
    ) == ("Model",)


def test_cancellation_before_synchronous_settle_prevents_recompute():
    document = _Document(readiness={"ready": False, "must_execute": True})

    def checkpoint(phase):
        if phase == "mutation_readiness_wait_before":
            raise RuntimeError("cancelled")

    inflight = SimpleNamespace(token=SimpleNamespace(checkpoint=checkpoint))

    with pytest.raises(RuntimeError, match="cancelled"):
        await_transient_mutation_readiness([document], inflight=inflight)

    assert document.recompute_calls == 0


@pytest.mark.parametrize(
    "readiness",
    [
        {"ready": False, "recomputing": True},
        {"ready": False, "notification_replay": True},
    ],
)
def test_async_transient_state_is_not_fake_waited_inside_running_gui_task(readiness):
    document = _Document(readiness=readiness)
    phases = []
    inflight = SimpleNamespace(
        token=SimpleNamespace(checkpoint=lambda phase: phases.append(phase))
    )

    result, waited = await_transient_mutation_readiness([document], inflight=inflight)

    assert waited is False
    assert result[0]["ready"] is False
    assert document.recompute_calls == 0
    assert phases == []


def test_pause_and_quarantine_are_immediate_not_waited_through():
    document = _Document()
    mutation_readiness.mark_quarantined(document, "rollback failed")
    automation_pause.request_local_pause_after_current()
    settle_calls = []

    readiness, waited = await_transient_mutation_readiness(
        [document], settle=lambda docs: settle_calls.append(tuple(docs))
    )

    assert waited is False
    assert settle_calls == []
    assert readiness[0]["reasons"] == ["document_quarantined", "automation_paused"]


def test_native_mutation_admission_settles_once_before_entering_commit():
    document = _Document(readiness={"ready": False, "must_execute": True})
    commits: list[str] = []

    class Native:
        @staticmethod
        def commit_compatibility_mutation(
            _name,
            callback,
            *,
            structural=False,
            postcondition=None,
        ):
            assert structural is False
            commits.append("commit")
            callback()
            document.recompute()
            assert postcondition is not None
            assert postcondition() is True
            return {"status": "Committed", "committed": True}

    collaborators = SimpleNamespace(
        freecad=SimpleNamespace(getDocument=lambda _name: document),
        commit_compatibility_mutation=Native.commit_compatibility_mutation,
        validate_document_invariants=lambda _document: None,
    )
    phases: list[str] = []
    inflight = SimpleNamespace(
        token=SimpleNamespace(checkpoint=lambda phase: phases.append(phase))
    )

    assert (
        run_cad_mutation(collaborators, "Model", lambda: True, inflight=inflight)
        is True
    )
    assert commits == ["commit"]
    assert document.recompute_calls == 2  # settle, then native postcondition
    assert phases == [
        "mutation_readiness_wait_before",
        "mutation_readiness_wait_after",
    ]


def test_deferred_native_mutation_admits_and_preserves_pending_recompute():
    document = _Document(readiness={"ready": False, "must_execute": True})
    policies: list[bool] = []

    def commit(_name, callback, *, structural=False, recompute=True):
        assert structural is False
        policies.append(recompute)
        callback()
        return {"status": "Committed", "committed": True}

    collaborators = SimpleNamespace(
        freecad=SimpleNamespace(getDocument=lambda _name: document),
        commit_compatibility_mutation=commit,
        validate_document_invariants=lambda _document: None,
    )

    result = run_cad_mutation(
        collaborators,
        "Model",
        lambda: {"ok": True, "recompute": {"deferred": True}},
        validate_after_callback=False,
        native_recompute=False,
    )

    assert result["ok"] is True
    assert result["recompute"]["deferred"] is True
    assert policies == [False]
    assert document.recompute_calls == 0
    assert document.getMutationReadiness()["must_execute"] is True


def test_already_admitted_deferred_mutation_may_finish_after_local_pause():
    document = _Document(readiness={"ready": False, "must_execute": True})
    admitted = automation_pause.admit_remote_write("repair_references", ("Model",))
    automation_pause.request_local_pause_after_current()
    calls: list[bool] = []

    def commit(_name, callback, *, structural=False, recompute=True):
        calls.append(recompute)
        callback()
        return {"status": "Committed", "committed": True}

    collaborators = SimpleNamespace(
        freecad=SimpleNamespace(getDocument=lambda _name: document),
        commit_compatibility_mutation=commit,
        validate_document_invariants=lambda _document: None,
    )

    result = run_cad_mutation(
        collaborators,
        "Model",
        lambda: {"ok": True},
        validate_after_callback=False,
        native_recompute=False,
    )

    assert result["ok"] is True
    assert calls == [False]
    automation_pause.finish_remote_write(admitted["token"])


def test_native_rejection_reports_readiness_and_quarantines_detected_rollback_failure():
    document = _Document()

    collaborators = SimpleNamespace(
        freecad=SimpleNamespace(getDocument=lambda _name: document),
        commit_compatibility_mutation=lambda *_args, **_kwargs: {
            "status": "RollbackFailed",
            "committed": False,
            "rollback_succeeded": False,
        },
        validate_document_invariants=lambda _document: None,
    )

    result = run_cad_mutation(collaborators, "Model", lambda: True)

    assert result["error_code"] == "NATIVE_COMPATIBILITY_MUTATION_REJECTED"
    assert result["mutation_readiness"][0]["reasons"] == ["document_quarantined"]
    assert result["retryable"] is False


def test_exception_from_failed_native_rollback_is_typed_and_quarantined():
    document = _Document()

    def failed_rollback(*_args, **_kwargs):
        document._readiness = _native_payload(
            ready=False,
            poisoned=True,
            diagnostic="rollback restore failed",
        )
        raise RuntimeError("rollback restore failed")

    collaborators = SimpleNamespace(
        freecad=SimpleNamespace(getDocument=lambda _name: document),
        commit_compatibility_mutation=failed_rollback,
        validate_document_invariants=lambda _document: None,
    )

    result = run_cad_mutation(collaborators, "Model", lambda: True)

    assert result["error_code"] == "TRANSACTION_ROLLBACK_FAILED"
    assert result["retryable"] is False
    assert result["diagnostic"] == "rollback restore failed"
    assert result["mutation_readiness"][0]["quarantined"] is True
    assert result["mutation_readiness"][0]["collaboration_poisoned"] is True


def test_ordinary_native_callback_exception_is_not_reclassified_as_rollback_failure():
    document = _Document()

    collaborators = SimpleNamespace(
        freecad=SimpleNamespace(getDocument=lambda _name: document),
        commit_compatibility_mutation=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("ordinary callback failure")
        ),
        validate_document_invariants=lambda _document: None,
    )

    with pytest.raises(RuntimeError, match="ordinary callback failure"):
        run_cad_mutation(collaborators, "Model", lambda: True)

    assert mutation_readiness.document_readiness(document)["quarantined"] is False


def test_undo_uses_the_same_pause_admission_gate():
    clear_operation_terminal_store()

    class HistoryDocument(_Document):
        def __init__(self):
            super().__init__()
            self.undo_calls = 0
            self.UndoNames = ["EditA"]
            self.UndoCount = 1

        def collaborationIdentity(self):
            return {
                "instance_id": 5,
                "lifecycle_epoch": 1,
                "state": "Live",
            }

        def undo(self):
            self.undo_calls += 1

    document = HistoryDocument()
    rpc = MagicMock()
    rpc._execution_collaborators.freecad.listDocuments.return_value = {
        "Model": document
    }
    rpc._execution_collaborators.request_identity_provider.return_value.get_request_identity.return_value = {
        "authenticated_session_id": "actor-1",
    }

    selector = {
        "document_uid": "uid-1",
        "document_instance_id": 5,
        "lifecycle_epoch": 1,
        "document_name": "Model",
    }
    head = capture_undo_head(document)
    undo_kwargs = dict(
        operation_id="undo-pause-blocked",
        expected_undo_count=head["undo_count"],
        expected_undo_head=head["undo_head"],
        freecad=rpc._execution_collaborators.freecad,
        rpc=rpc,
    )

    automation_pause.request_local_pause_after_current()

    blocked = undo_gui(selector, **undo_kwargs)

    assert blocked["error_code"] == "MUTATION_NOT_READY"
    assert document.undo_calls == 0

    automation_pause._paused = False
    admitted = automation_pause.admit_remote_write("undo", ("Model",))
    automation_pause.request_local_pause_after_current()
    result = undo_gui(
        selector,
        operation_id="undo-pause-admitted",
        expected_undo_count=head["undo_count"],
        expected_undo_head=head["undo_head"],
        freecad=rpc._execution_collaborators.freecad,
        rpc=rpc,
    )
    assert result.get("success") is True
    assert document.undo_calls == 1
    automation_pause.finish_remote_write(admitted["token"])


@pytest.mark.parametrize(
    "blocker",
    ["quarantined", "poisoned", "paused", "recomputing", "native_not_ready"],
)
def test_recompute_and_wait_rejection_never_recomputes_or_flushes(blocker):
    readiness = {}
    if blocker == "poisoned":
        readiness = {"ready": False, "poisoned": True}
    elif blocker == "recomputing":
        readiness = {"ready": False, "recomputing": True}
    elif blocker == "native_not_ready":
        readiness = {"ready": False}
    document = _Document(readiness=readiness)
    if blocker == "quarantined":
        mutation_readiness.mark_quarantined(document, "rollback failed")
    elif blocker == "paused":
        automation_pause.request_local_pause_after_current()

    leaf_calls: list[str] = []
    collaborators = SimpleNamespace(
        freecad=SimpleNamespace(getDocument=lambda _name: document),
        recompute_and_wait=lambda _name: (
            leaf_calls.extend(("recompute", "flush")) or {"ok": True}
        ),
    )

    result = recompute_and_wait_gui("Model", collaborators=collaborators)

    assert result["error_code"] == "MUTATION_NOT_READY"
    assert leaf_calls == []
    assert document.recompute_calls == 0


def test_recompute_and_wait_healthy_path_recomputes_and_flushes_once():
    document = _Document()
    leaf_calls: list[str] = []

    def recompute_and_flush(_name):
        document.recompute()
        leaf_calls.extend(("recompute", "flush"))
        return {"ok": True, "idle": True}

    result = recompute_and_wait_gui(
        "Model",
        collaborators=SimpleNamespace(
            freecad=SimpleNamespace(getDocument=lambda _name: document),
            recompute_and_wait=recompute_and_flush,
        ),
    )

    assert result == {"ok": True, "idle": True}
    assert leaf_calls == ["recompute", "flush"]
    assert document.recompute_calls == 1
