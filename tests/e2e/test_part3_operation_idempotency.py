"""E2E: Part 3 operation idempotency and safe undo/redo history semantics."""

from __future__ import annotations

import uuid

import pytest

FreeCAD = pytest.importorskip("FreeCAD")

from addon.FreeCADMCP.part3_collaboration.history_head import capture_undo_head
from addon.FreeCADMCP.rpc_server import request_identity
from tests.conftest import (
    LiveFreeCADConnection,
    _missing_branch_native_document_apis,
    _reject_missing_branch_native_document_apis,
)
from tests.e2e.test_part3_checked_edit import _build_authenticated_rpc, _selector

pytestmark = [pytest.mark.e2e]

_PROP_NO_RECOMPUTE = 16


@pytest.fixture
def part3_history_doc():
    doc_name = f"Part3History_{uuid.uuid4().hex[:8]}"
    conn = LiveFreeCADConnection(doc_name)
    missing_apis = _missing_branch_native_document_apis(conn.doc)
    if missing_apis:
        conn.close()
        _reject_missing_branch_native_document_apis(missing_apis)

    stress = conn.doc.addObject("App::FeatureTest", "StressBox")
    stress.Integer = 1
    stress.Float = 2.0
    conn.doc.recompute()

    def first_edit():
        conn.doc.StressBox.Integer = 5

    assert conn.doc.commitCompatibilityMutation(first_edit).get("committed") is True

    rpc, _, _ = _build_authenticated_rpc(conn)
    yield conn, rpc
    request_identity.clear_request_identity()
    if doc_name in FreeCAD.listDocuments():
        FreeCAD.closeDocument(doc_name)


def test_commit_checked_property_lost_response_retry(part3_history_doc):
    conn, rpc = part3_history_doc
    selector = _selector(conn.doc)
    revision_keys = [{"kind": "ObjectModel", "subject": "StressBox"}]

    begin = rpc._dispatch(
        "begin_checked_edit",
        [selector, revision_keys, "history-begin-retry"],
    )
    assert begin.get("success") is True, begin
    session_id = begin["session_id"]
    before_float = conn.doc.StressBox.Float

    commit_args = [
        session_id,
        selector,
        "StressBox",
        "Float",
        "float",
        "42.0",
        "history-commit-retry",
    ]
    first = rpc._dispatch("commit_checked_property", commit_args)
    assert first.get("success") is True, first
    assert conn.doc.StressBox.Float == 42.0

    retry = rpc._dispatch("commit_checked_property", commit_args)
    assert retry.get("success") is True, retry
    assert retry == first
    assert conn.doc.StressBox.Float == 42.0
    assert conn.doc.StressBox.Float != before_float


def test_undo_refuses_after_intervening_local_edit(part3_history_doc):
    conn, rpc = part3_history_doc
    selector = _selector(conn.doc)
    head = capture_undo_head(conn.doc)

    refused = rpc._dispatch(
        "undo",
        [
            selector,
            "history-undo-intervene",
            head["undo_count"],
            head["undo_head"],
        ],
    )
    assert refused.get("success") is True, refused
    assert conn.doc.StressBox.Integer == 1

    def local_edit():
        conn.doc.StressBox.Integer = 77

    assert conn.doc.commitCompatibilityMutation(local_edit).get("committed") is True
    assert conn.doc.StressBox.Integer == 77

    stale_head = capture_undo_head(conn.doc)
    retry = rpc._dispatch(
        "undo",
        [
            selector,
            "history-undo-stale-head",
            head["undo_count"],
            head["undo_head"],
        ],
    )
    assert retry.get("success") is False, retry
    assert retry.get("error_code") == "HISTORY_HEAD_REJECTED"
    assert conn.doc.StressBox.Integer == 77
    assert stale_head["undo_head"] != head["undo_head"]
