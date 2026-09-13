"""Unit tests for the Part 3 (session, operation_id) terminal-result store."""

from __future__ import annotations

import pytest

from addon.FreeCADMCP.part3_collaboration.operation_terminal_store import (
    check_operation_terminal,
    clear_operation_terminal_store,
    store_operation_terminal,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_store():
    clear_operation_terminal_store()
    yield
    clear_operation_terminal_store()


def test_equal_payload_replay_returns_stored_terminal() -> None:
    payload = {"method": "undo", "doc_selector": {"document_uid": "uid-1"}}
    terminal = {"success": True, "operation_id": "op-1"}
    store_operation_terminal(
        "session-a",
        "op-1",
        payload,
        document_instance_id=2,
        lifecycle_epoch=1,
        terminal_result=terminal,
    )
    replay = check_operation_terminal(
        "session-a",
        "op-1",
        payload,
        live_document_instance_id=2,
        live_lifecycle_epoch=1,
    )
    assert replay.state == "replay"
    assert replay.terminal_result == terminal


def test_unequal_payload_is_protocol_conflict() -> None:
    store_operation_terminal(
        "session-a",
        "op-1",
        {"method": "undo", "expected_undo_count": 1},
        document_instance_id=2,
        lifecycle_epoch=1,
        terminal_result={"success": True},
    )
    replay = check_operation_terminal(
        "session-a",
        "op-1",
        {"method": "undo", "expected_undo_count": 2},
        live_document_instance_id=2,
        live_lifecycle_epoch=1,
    )
    assert replay.state == "conflict"


def test_stale_lifecycle_refuses_replay() -> None:
    store_operation_terminal(
        "session-a",
        "op-1",
        {"method": "undo"},
        document_instance_id=2,
        lifecycle_epoch=1,
        terminal_result={"success": True},
    )
    replay = check_operation_terminal(
        "session-a",
        "op-1",
        {"method": "undo"},
        live_document_instance_id=3,
        live_lifecycle_epoch=2,
    )
    assert replay.state == "stale_lifecycle"
