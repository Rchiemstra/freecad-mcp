"""Unit tests for Part 3 operation idempotency and history-head safety."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from addon.FreeCADMCP.part3_collaboration.checked_edit_fence import (
    clear_begin_fences,
    store_begin_fence,
)
from addon.FreeCADMCP.part3_collaboration.history_head import capture_undo_head
from addon.FreeCADMCP.part3_collaboration.operation_terminal_store import (
    clear_operation_terminal_store,
)
from addon.FreeCADMCP.rpc_server import request_identity
from addon.FreeCADMCP.rpc_server.methods import part3_collaboration_methods as methods
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import recompute_helpers
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.recompute_helpers import undo_gui

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_stores():
    clear_begin_fences()
    clear_operation_terminal_store()
    yield
    clear_begin_fences()
    clear_operation_terminal_store()


@pytest.fixture(autouse=True)
def _cad_mutation_gates():
    with (
        patch(
            "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.recompute_helpers.admit_cad_mutation",
            return_value=None,
        ),
        patch(
            "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.recompute_helpers.postflight_cad_mutation",
            side_effect=lambda _doc, result: result,
        ),
    ):
        yield


def _mock_document(**overrides):
    document = MagicMock()
    document.editSessionStatus.return_value = {
        "status": "Active",
        "actor_id": "runtime-owner",
    }
    document.collaborationIdentity.return_value = {
        "instance_id": 5,
        "lifecycle_epoch": 1,
        "state": "Live",
    }
    document.Uid = SimpleNamespace(Value="uid-1")
    document.Name = "Model"
    for key, value in overrides.items():
        setattr(document, key, value)
    return document


def _mock_rpc(document):
    rpc = MagicMock()
    rpc._execution_collaborators.freecad.listDocuments.return_value = {"Model": document}
    rpc._execution_collaborators.request_identity_provider.return_value.get_request_identity.return_value = {
        "authenticated_session_id": "auth-a",
        "instance_id": "runtime-owner",
    }
    return rpc


def _set_request_identity(rpc, *, auth_session: str, runtime: str | None) -> None:
    identity = {"authenticated_session_id": auth_session}
    if runtime is not None:
        identity["instance_id"] = runtime
    rpc._execution_collaborators.request_identity_provider.return_value.get_request_identity.return_value = identity


@pytest.mark.parametrize("action", ["undo", "redo"])
def test_history_action_carries_authenticated_actor_across_gui_thread(action) -> None:
    document = _mock_document()
    history_name = "EditA"
    setattr(document, f"{action.title()}Names", [history_name])
    setattr(document, f"{action.title()}Count", 1)
    setattr(document, action, MagicMock())
    rpc = _mock_rpc(document)
    rpc._cad_collaborators.freecad = rpc._execution_collaborators.freecad
    rpc._execution_collaborators.request_identity_provider.return_value = request_identity
    rpc._adapt_gui_mutation_result.side_effect = lambda result: result
    thread_ids = {}

    def dispatch_on_gui_thread(callback):
        captured = {}

        def run_callback():
            thread_ids["gui"] = threading.get_ident()
            captured["result"] = callback()

        thread = threading.Thread(target=run_callback)
        thread.start()
        thread.join()
        assert not thread.is_alive()
        return captured["result"]

    rpc._dispatch_gui.side_effect = dispatch_on_gui_thread
    selector = {
        "document_uid": "uid-1",
        "document_instance_id": 5,
        "lifecycle_epoch": 1,
        "document_name": "Model",
    }
    expected = {
        f"expected_{action}_count": 1,
        f"expected_{action}_head": history_name,
    }

    thread_ids["handler"] = threading.get_ident()
    request_identity.set_request_identity(
        authenticated_session_id="auth-a",
        instance_id="runtime-owner",
    )
    try:
        result = getattr(recompute_helpers, action)(
            rpc,
            selector,
            f"{action}-thread-hop",
            **expected,
        )
    finally:
        request_identity.clear_request_identity()

    assert thread_ids["handler"] != thread_ids["gui"]
    assert result.get("success") is True, result
    getattr(document, action).assert_called_once()


def test_commit_checked_property_replay_skips_prepare() -> None:
    store_begin_fence(
        "session-abc",
        document_instance_id=5,
        lifecycle_epoch=1,
        revisions=[{"kind": "ObjectModel", "subject": "StressBox", "revision": 4}],
    )
    document = _mock_document()
    document.prepareEditWithExpectedRevisions.return_value = object()
    document.commitEdit.return_value = {
        "status": "Committed",
        "committed": True,
        "published_revisions": [],
    }
    rpc = _mock_rpc(document)
    selector = {
        "document_uid": "uid-1",
        "document_instance_id": 5,
        "lifecycle_epoch": 1,
        "document_name": "Model",
    }
    args = [
        "session-abc",
        selector,
        "StressBox",
        "Float",
        "float",
        "3.0",
        "op-1",
    ]

    first = methods.commit_checked_property(rpc, *args)
    assert first.get("success") is True, first
    document.prepareEditWithExpectedRevisions.assert_called_once()

    second = methods.commit_checked_property(rpc, *args)
    assert second.get("success") is True, second
    assert second == first
    document.prepareEditWithExpectedRevisions.assert_called_once()


def test_commit_checked_property_payload_conflict() -> None:
    store_begin_fence(
        "session-abc",
        document_instance_id=5,
        lifecycle_epoch=1,
        revisions=[{"kind": "ObjectModel", "subject": "StressBox", "revision": 4}],
    )
    document = _mock_document()
    document.prepareEditWithExpectedRevisions.return_value = object()
    document.commitEdit.return_value = {
        "status": "Committed",
        "committed": True,
        "published_revisions": [],
    }
    rpc = _mock_rpc(document)
    selector = {
        "document_uid": "uid-1",
        "document_instance_id": 5,
        "lifecycle_epoch": 1,
        "document_name": "Model",
    }

    first = methods.commit_checked_property(
        rpc,
        "session-abc",
        selector,
        "StressBox",
        "Float",
        "float",
        "3.0",
        "op-conflict",
    )
    assert first.get("success") is True, first

    conflict = methods.commit_checked_property(
        rpc,
        "session-abc",
        selector,
        "StressBox",
        "Float",
        "float",
        "9.0",
        "op-conflict",
    )
    assert conflict.get("success") is False, conflict
    assert conflict.get("error_code") == "OPERATION_PAYLOAD_CONFLICT"


def test_undo_refuses_intervening_local_history_change() -> None:
    document = _mock_document()
    document.UndoNames = ["FirstEdit"]
    document.UndoCount = 1
    document.undo = MagicMock()
    rpc = _mock_rpc(document)
    selector = {
        "document_uid": "uid-1",
        "document_instance_id": 5,
        "lifecycle_epoch": 1,
        "document_name": "Model",
    }

    refused = undo_gui(
        selector,
        operation_id="undo-op-1",
        expected_undo_count=1,
        expected_undo_head="FirstEdit",
        freecad=rpc._execution_collaborators.freecad,
        rpc=rpc,
    )
    assert refused.get("success") is True, refused
    document.undo.assert_called_once()
    document.recompute.assert_called_once()

    document.UndoNames = ["LocalIntervention"]
    document.UndoCount = 1
    document.undo.reset_mock()
    document.recompute.reset_mock()

    retry = undo_gui(
        selector,
        operation_id="undo-op-2",
        expected_undo_count=1,
        expected_undo_head="FirstEdit",
        freecad=rpc._execution_collaborators.freecad,
        rpc=rpc,
    )
    assert retry.get("success") is False, retry
    assert retry.get("error_code") == "HISTORY_HEAD_REJECTED"
    document.undo.assert_not_called()
    document.recompute.assert_not_called()


def test_undo_replay_returns_stored_terminal_without_second_undo() -> None:
    document = _mock_document()
    document.UndoNames = ["EditA"]
    document.UndoCount = 1
    document.undo = MagicMock()
    rpc = _mock_rpc(document)
    selector = {
        "document_uid": "uid-1",
        "document_instance_id": 5,
        "lifecycle_epoch": 1,
        "document_name": "Model",
    }
    head = capture_undo_head(document)

    first = undo_gui(
        selector,
        operation_id="undo-replay",
        expected_undo_count=head["undo_count"],
        expected_undo_head=head["undo_head"],
        freecad=rpc._execution_collaborators.freecad,
        rpc=rpc,
    )
    assert first.get("success") is True, first
    document.undo.assert_called_once()

    document.undo.reset_mock()
    _set_request_identity(rpc, auth_session="auth-b", runtime="runtime-owner")
    second = undo_gui(
        selector,
        operation_id="undo-replay",
        expected_undo_count=head["undo_count"],
        expected_undo_head=head["undo_head"],
        freecad=rpc._execution_collaborators.freecad,
        rpc=rpc,
    )
    assert second.get("success") is True, second
    assert second == first
    document.undo.assert_not_called()


def test_cancel_checked_edit_replay_after_success_without_active_session() -> None:
    document = _mock_document()
    document.cancelEdit.return_value = True
    rpc = _mock_rpc(document)

    first = methods.cancel_checked_edit(
        rpc,
        "session-cancel",
        "cleanup",
        "cancel-replay-op",
    )
    assert first.get("success") is True, first
    document.cancelEdit.assert_called_once()

    document.editSessionStatus.return_value = {"status": "Inactive"}
    document.cancelEdit.reset_mock()
    _set_request_identity(rpc, auth_session="auth-b", runtime="runtime-owner")

    second = methods.cancel_checked_edit(
        rpc,
        "session-cancel",
        "cleanup",
        "cancel-replay-op",
    )
    assert second.get("success") is True, second
    assert second == first
    document.cancelEdit.assert_not_called()


def test_begin_replay_survives_bearer_rotation_for_same_runtime() -> None:
    document = _mock_document()
    document.beginEditSession.return_value = {"session_id": "native-edit-1"}
    document.snapshotForEdit.return_value = {
        "document_instance_id": 5,
        "lifecycle_epoch": 1,
        "revisions": [
            {"kind": "ObjectModel", "subject": "StressBox", "revision": 4}
        ],
    }
    rpc = _mock_rpc(document)
    selector = {
        "document_uid": "uid-1",
        "document_instance_id": 5,
        "lifecycle_epoch": 1,
        "document_name": "Model",
    }

    first = methods.begin_checked_edit(
        rpc,
        selector,
        [{"kind": "ObjectModel", "subject": "StressBox"}],
        "begin-renewal",
    )
    _set_request_identity(rpc, auth_session="auth-b", runtime="runtime-owner")
    second = methods.begin_checked_edit(
        rpc,
        selector,
        [{"kind": "ObjectModel", "subject": "StressBox"}],
        "begin-renewal",
    )

    assert first.get("success") is True, first
    assert second == first
    document.beginEditSession.assert_called_once_with("runtime-owner")
    document.snapshotForEdit.assert_called_once()


def test_commit_terminal_replay_survives_bearer_rotation_for_same_runtime() -> None:
    store_begin_fence(
        "native-edit-1",
        document_instance_id=5,
        lifecycle_epoch=1,
        revisions=[{"kind": "ObjectModel", "subject": "StressBox", "revision": 4}],
    )
    document = _mock_document()
    document.prepareEditWithExpectedRevisions.return_value = object()
    document.commitEdit.return_value = {
        "status": "Committed",
        "committed": True,
        "published_revisions": [],
    }
    rpc = _mock_rpc(document)
    selector = {
        "document_uid": "uid-1",
        "document_instance_id": 5,
        "lifecycle_epoch": 1,
        "document_name": "Model",
    }
    args = [
        "native-edit-1",
        selector,
        "StressBox",
        "Float",
        "float",
        "3.0",
        "commit-renewal",
    ]

    first = methods.commit_checked_property(rpc, *args)
    _set_request_identity(rpc, auth_session="auth-b", runtime="runtime-owner")
    second = methods.commit_checked_property(rpc, *args)

    assert first.get("success") is True, first
    assert second == first
    document.prepareEditWithExpectedRevisions.assert_called_once()
    document.commitEdit.assert_called_once()


def test_checked_edit_continues_after_same_runtime_bearer_rotation() -> None:
    document = _mock_document()
    document.beginEditSession.return_value = {"session_id": "native-edit-1"}
    document.snapshotForEdit.return_value = {
        "document_instance_id": 5,
        "lifecycle_epoch": 1,
        "revisions": [
            {"kind": "ObjectModel", "subject": "StressBox", "revision": 4}
        ],
    }
    document.prepareEditWithExpectedRevisions.return_value = object()
    document.commitEdit.return_value = {
        "status": "Committed",
        "committed": True,
        "published_revisions": [],
    }
    rpc = _mock_rpc(document)
    selector = {
        "document_uid": "uid-1",
        "document_instance_id": 5,
        "lifecycle_epoch": 1,
        "document_name": "Model",
    }

    begun = methods.begin_checked_edit(
        rpc,
        selector,
        [{"kind": "ObjectModel", "subject": "StressBox"}],
        "begin-continuation",
    )
    _set_request_identity(rpc, auth_session="auth-b", runtime="runtime-owner")
    committed = methods.commit_checked_property(
        rpc,
        begun["session_id"],
        selector,
        "StressBox",
        "Float",
        "float",
        "3.0",
        "commit-continuation",
    )

    assert begun.get("success") is True, begun
    assert committed.get("success") is True, committed
    document.beginEditSession.assert_called_once_with("runtime-owner")
    document.prepareEditWithExpectedRevisions.assert_called_once()
    document.commitEdit.assert_called_once()


def test_missing_stable_runtime_identity_fails_closed() -> None:
    document = _mock_document()
    document.beginEditSession.return_value = {"session_id": "native-edit-1"}
    document.snapshotForEdit.return_value = {
        "document_instance_id": 5,
        "lifecycle_epoch": 1,
        "revisions": [],
    }
    rpc = _mock_rpc(document)
    _set_request_identity(rpc, auth_session="auth-a", runtime=None)

    result = methods.begin_checked_edit(
        rpc,
        {
            "document_uid": "uid-1",
            "document_instance_id": 5,
            "lifecycle_epoch": 1,
            "document_name": "Model",
        },
        [{"kind": "ObjectModel", "subject": "StressBox"}],
        "begin-without-runtime",
    )

    assert result.get("success") is False, result
    assert result.get("error_code") == "LEASE_PROTOCOL_REQUIRED"
    document.beginEditSession.assert_not_called()
