"""E2E: Part 3 identity-bound checked-edit RPCs via native collaboration."""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

FreeCAD = pytest.importorskip("FreeCAD")

from addon.FreeCADMCP.rpc_server import request_identity
from addon.FreeCADMCP.rpc_server.lease_protocol import RequestEnvelope
from tests.conftest import (
    LiveFreeCADConnection,
    _missing_branch_native_document_apis,
    _reject_missing_branch_native_document_apis,
)

pytestmark = [pytest.mark.e2e]

_PROP_NO_RECOMPUTE = 16


class _SessionManager:
    def __init__(self, runtime_id: str):
        self.runtime_id = runtime_id
        self.session_ids: dict[str, str] = {}

    def authenticate(self, session_token, mcp_runtime_id=None):
        del mcp_runtime_id
        session_id = self.session_ids.setdefault(session_token, str(uuid.uuid4()))
        return SimpleNamespace(
            session_id=session_id,
            mcp=SimpleNamespace(process_started_at="2026-08-17T00:00:00Z"),
        )


def _build_authenticated_rpc(conn: LiveFreeCADConnection):
    import threading

    from addon.FreeCADMCP.dispatch.inflight_request_registry import (
        InflightRequestRegistry,
    )
    from addon.FreeCADMCP.rpc_server import rpc_server as rpc_server_module
    from addon.FreeCADMCP.transport.replay import RequestReplayCache
    from tests.conftest import _InlineGuiDispatcher

    replay_cache = RequestReplayCache()
    inflight_requests = InflightRequestRegistry()
    runtime_id = str(uuid.uuid4())
    session_manager = _SessionManager(runtime_id)
    session_token = str(uuid.uuid4())
    request_identity.set_request_identity(
        instance_id=runtime_id,
        rpc_session_token=session_token,
    )
    collaboration = rpc_server_module._build_collaboration_collaborators(
        runtime_manifest=None,
        inflight_request_registry=inflight_requests,
        request_replay_cache=replay_cache,
        runtime_id=runtime_id,
    )
    execution = rpc_server_module._build_execution_collaborators(
        compatibility_api=collaboration.compatibility_api,
        gui_dispatcher_value=_InlineGuiDispatcher(),
        worker_manager_value=None,
        shutdown_requested_value=threading.Event(),
        request_replay_cache=replay_cache,
        inflight_request_registry=inflight_requests,
        session_manager_value=session_manager,
        runtime_manifest_value=None,
        actual_endpoint_value=None,
        runtime_id_value=runtime_id,
        server_started_at_value="",
    )
    rpc = rpc_server_module.FreeCADRPC(
        allow_execute_code=True,
        collaboration_collaborators=collaboration,
        execution_collaborators=execution,
    )
    return rpc, session_token, runtime_id


def _selector(document) -> dict[str, object]:
    identity = document.collaborationIdentity()
    uid = getattr(document, "Uid", None)
    uid_value = getattr(uid, "Value", uid)
    return {
        "document_uid": str(uid_value or ""),
        "document_instance_id": int(identity["instance_id"]),
        "lifecycle_epoch": int(identity["lifecycle_epoch"]),
        "document_name": str(document.Name),
    }


def _model_key(object_name: str) -> dict[str, str]:
    return {"kind": "ObjectModel", "subject": object_name}


def _property_key(object_name: str, property_name: str) -> dict[str, str]:
    return {
        "kind": "ObjectProperty",
        "subject": object_name,
        "property_name": property_name,
    }


@pytest.fixture
def part3_doc():
    doc_name = f"Part3Checked_{uuid.uuid4().hex[:8]}"
    conn = LiveFreeCADConnection(doc_name)
    missing_apis = _missing_branch_native_document_apis(conn.doc)
    if missing_apis:
        conn.close()
        _reject_missing_branch_native_document_apis(missing_apis)

    stress = conn.doc.addObject("App::FeatureTest", "StressBox")
    stress.Integer = 1
    stress.Float = 2.0

    second = conn.doc.addObject("App::DocumentObject", "SecondBox")
    second.addProperty(
        "App::PropertyInteger",
        "BetaValue",
        "Data",
        "",
        _PROP_NO_RECOMPUTE,
    )
    second.BetaValue = 0

    conn.doc.recompute()
    rpc, session_token, runtime_id = _build_authenticated_rpc(conn)
    yield conn, rpc, session_token, runtime_id
    request_identity.clear_request_identity()
    if doc_name in FreeCAD.listDocuments():
        FreeCAD.closeDocument(doc_name)


def test_same_property_conflict_via_checked_edit(part3_doc):
    conn, rpc, _, _ = part3_doc
    selector = _selector(conn.doc)
    revision_keys = [_model_key("StressBox")]

    begin = rpc._dispatch(
        "begin_checked_edit",
        [selector, revision_keys, "part3-conflict-begin"],
    )
    assert begin.get("success") is True, begin
    session_id = begin["session_id"]

    def mutate_integer():
        conn.doc.StressBox.Integer = 99

    mutation = conn.doc.commitCompatibilityMutation(
        mutate_integer,
        object_name="StressBox",
    )
    assert mutation.get("committed") is True, mutation

    conflict = rpc._dispatch(
        "commit_checked_property",
        [
            session_id,
            selector,
            "StressBox",
            "Float",
            "float",
            "20.0",
            "part3-conflict-op",
        ],
    )
    assert conflict.get("success") is False, conflict
    assert conflict.get("error_code") == "DOCUMENT_CONFLICT"
    assert "ObjectModel:StressBox" in conflict.get("changed_semantic_keys", [])
    assert isinstance(conflict.get("expected_revisions"), dict)
    assert isinstance(conflict.get("current_revisions"), dict)

    status = conn.doc.editSessionStatus(session_id)
    assert status is not None
    rpc._dispatch("cancel_checked_edit", [session_id, "test cleanup", "part3-conflict-cancel"])


def test_independent_property_success(part3_doc):
    conn, rpc, _, _ = part3_doc
    selector = _selector(conn.doc)
    revision_keys = [_property_key("SecondBox", "BetaValue")]

    begin = rpc._dispatch("begin_checked_edit", [selector, revision_keys, "part3-independent-begin"])
    assert begin.get("success") is True, begin
    session_id = begin["session_id"]

    def mutate_alpha():
        conn.doc.StressBox.Integer = 10

    assert conn.doc.commitCompatibilityMutation(mutate_alpha).get("committed") is True

    success = rpc._dispatch(
        "commit_checked_property",
        [
            session_id,
            selector,
            "SecondBox",
            "BetaValue",
            "integer",
            "30",
            "part3-independent-op",
        ],
    )
    assert success.get("success") is True, success
    assert success.get("committed") is True, success
    assert conn.doc.StressBox.Integer == 10
    assert conn.doc.SecondBox.BetaValue == 30


def test_close_reopen_refuses_stale_selector_and_session(part3_doc):
    conn, rpc, _, _ = part3_doc
    selector = _selector(conn.doc)
    revision_keys = [_model_key("StressBox")]

    begin = rpc._dispatch("begin_checked_edit", [selector, revision_keys, "part3-stale-begin"])
    assert begin.get("success") is True, begin
    session_id = begin["session_id"]

    save_path = Path(tempfile.gettempdir()) / f"part3_{uuid.uuid4().hex}.FCStd"
    conn.doc.saveAs(str(save_path))
    doc_name = conn.doc.Name
    FreeCAD.closeDocument(doc_name)
    reopened = FreeCAD.openDocument(str(save_path))

    stale_commit = rpc._dispatch(
        "commit_checked_property",
        [
            session_id,
            selector,
            "StressBox",
            "Integer",
            "integer",
            "5",
            "part3-stale-op",
        ],
    )
    assert stale_commit.get("success") is False, stale_commit
    assert stale_commit.get("error_code") == "DOCUMENT_LIFECYCLE_REJECTED"

    stale_cancel = rpc._dispatch("cancel_checked_edit", [session_id, "cleanup", "part3-stale-cancel"])
    assert stale_cancel.get("success") is False, stale_cancel
    assert stale_cancel.get("error_code") == "DOCUMENT_LIFECYCLE_REJECTED"

    new_selector = _selector(reopened)
    stale_selector_read = rpc._dispatch("get_semantic_revisions", [selector, revision_keys])
    assert stale_selector_read.get("success") is False, stale_selector_read
    assert stale_selector_read.get("error_code") == "DOCUMENT_LIFECYCLE_REJECTED"

    fresh_read = rpc._dispatch("get_semantic_revisions", [new_selector, revision_keys])
    assert fresh_read.get("success") is True, fresh_read

    FreeCAD.closeDocument(reopened.Name)
    save_path.unlink(missing_ok=True)
