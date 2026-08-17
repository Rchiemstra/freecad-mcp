"""Unit tests for checked-edit begin-time revision fence store."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from addon.FreeCADMCP.part3_collaboration.checked_edit_fence import (
    clear_begin_fences,
    discard_begin_fence,
    pop_begin_fence,
    store_begin_fence,
)
from addon.FreeCADMCP.rpc_server.methods import part3_collaboration_methods as methods

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_fence_store():
    clear_begin_fences()
    yield
    clear_begin_fences()


def test_store_and_pop_begin_fence() -> None:
    store_begin_fence(
        "session-1",
        document_instance_id=3,
        lifecycle_epoch=2,
        revisions=[{"kind": "ObjectModel", "subject": "StressBox", "revision": 1}],
    )
    fence = pop_begin_fence("session-1")
    assert fence is not None
    assert fence.document_instance_id == 3
    assert fence.lifecycle_epoch == 2
    assert fence.revisions[0]["revision"] == 1
    assert pop_begin_fence("session-1") is None


def test_commit_checked_property_uses_begin_fence_for_prepare() -> None:
    store_begin_fence(
        "session-abc",
        document_instance_id=5,
        lifecycle_epoch=1,
        revisions=[{"kind": "ObjectModel", "subject": "StressBox", "revision": 4}],
    )

    document = MagicMock()
    document.editSessionStatus.return_value = {"status": "Active"}
    document.collaborationIdentity.return_value = {
        "instance_id": 5,
        "lifecycle_epoch": 1,
        "state": "Live",
    }
    document.Uid = SimpleNamespace(Value="uid-1")
    document.Name = "Model"
    document.prepareEditWithExpectedRevisions.return_value = object()
    document.commitEdit.return_value = {
        "status": "Committed",
        "committed": True,
        "published_revisions": [],
    }

    rpc = MagicMock()
    rpc._execution_collaborators.freecad.listDocuments.return_value = {"Model": document}
    rpc._execution_collaborators.request_identity_provider.return_value.get_request_identity.return_value = {
        "authenticated_session_id": "actor-1",
    }

    result = methods.commit_checked_property(
        rpc,
        "session-abc",
        {
            "document_uid": "uid-1",
            "document_instance_id": 5,
            "lifecycle_epoch": 1,
            "document_name": "Model",
        },
        "StressBox",
        "Float",
        "float",
        "3.0",
        "op-1",
    )

    assert result.get("success") is True, result
    document.prepareEditWithExpectedRevisions.assert_called_once()
    args = document.prepareEditWithExpectedRevisions.call_args[0]
    assert args[0] == "session-abc"
    assert args[1] == "op-1"
    assert args[4] == [{"kind": "ObjectModel", "subject": "StressBox", "revision": 4}]
    document.prepareEdit.assert_not_called()
    assert pop_begin_fence("session-abc") is None


def test_cancel_checked_property_discards_fence() -> None:
    store_begin_fence(
        "session-cancel",
        document_instance_id=1,
        lifecycle_epoch=1,
        revisions=[{"kind": "ObjectModel", "subject": "StressBox", "revision": 0}],
    )

    document = MagicMock()
    document.editSessionStatus.return_value = {"status": "Active"}
    document.collaborationIdentity.return_value = {
        "instance_id": 1,
        "lifecycle_epoch": 1,
        "state": "Live",
    }
    document.Uid = SimpleNamespace(Value="uid-1")
    document.Name = "Model"
    document.cancelEdit.return_value = True

    rpc = MagicMock()
    rpc._execution_collaborators.freecad.listDocuments.return_value = {"Model": document}
    rpc._execution_collaborators.request_identity_provider.return_value.get_request_identity.return_value = {
        "authenticated_session_id": "actor-1",
    }

    result = methods.cancel_checked_edit(rpc, "session-cancel", "cleanup", "cancel-op-1")
    assert result.get("success") is True, result
    assert pop_begin_fence("session-cancel") is None
