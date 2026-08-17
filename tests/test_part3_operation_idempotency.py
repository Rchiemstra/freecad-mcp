"""Unit tests for Part 3 operation idempotency and history-head safety."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from addon.FreeCADMCP.part3_collaboration.checked_edit_fence import (
    clear_begin_fences,
    pop_begin_fence,
    store_begin_fence,
)
from addon.FreeCADMCP.part3_collaboration.history_head import capture_undo_head
from addon.FreeCADMCP.part3_collaboration.operation_terminal_store import (
    clear_operation_terminal_store,
)
from addon.FreeCADMCP.rpc_server.methods import part3_collaboration_methods as methods
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
    document.editSessionStatus.return_value = {"status": "Active"}
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
        "authenticated_session_id": "actor-1",
    }
    return rpc


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

    second = methods.cancel_checked_edit(
        rpc,
        "session-cancel",
        "cleanup",
        "cancel-replay-op",
    )
    assert second.get("success") is True, second
    assert second == first
    document.cancelEdit.assert_not_called()
