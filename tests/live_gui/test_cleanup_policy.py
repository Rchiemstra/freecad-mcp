"""Unit checks for the live suite's narrowly scoped retry policy."""

from unittest.mock import Mock

import pytest

from tests.live_gui._support import McpClient, ToolResult, assert_ok

pytestmark = pytest.mark.unit

_MESSAGE = "one or more semantic revisions changed before commit"


def _conflict(**changes):
    payload = {
        "contract_version": 1, "success": False, "ok": False,
        "outcome": "rejected", "committed": False, "retry_safe": True,
        "error_code": "NATIVE_COMPATIBILITY_MUTATION_REJECTED",
        "native_status": "Conflict", "native_message": _MESSAGE, "error": _MESSAGE,
    }
    payload.update(changes)
    return ToolResult("preview_attachment", True, _MESSAGE, payload)


def _client(monkeypatch, *results):
    client = McpClient.__new__(McpClient)
    client.gui_request_timed_out = False
    call = Mock(side_effect=results)
    monkeypatch.setattr(client, "_call", call)
    monkeypatch.setattr(client, "_run", lambda result: result)
    return client, call


def test_preview_retries_exact_preapply_conflict_once(monkeypatch, caplog):
    success = ToolResult("preview_attachment", False, "ok", {"success": True})
    client, call = _client(monkeypatch, _conflict(), success)
    args = {"doc_name": "LiveAttach", "datum_name": "OffsetPlane"}
    assert client.call("preview_attachment", **args) is success
    assert call.call_count == 2
    assert call.call_args_list[0] == call.call_args_list[1]
    assert "retrying once" in caplog.text


def test_second_preapply_conflict_still_fails(monkeypatch):
    conflict = _conflict()
    client, call = _client(monkeypatch, conflict, conflict)
    with pytest.raises(AssertionError, match=_MESSAGE):
        assert_ok(client.call("preview_attachment", doc_name="LiveAttach"))
    assert call.call_count == 2


@pytest.mark.parametrize("changes", [
    {"native_status": "ApplyFailed"}, {"native_message": _MESSAGE + "."},
    {"committed": True}, {"committed": None}, {"outcome": "uncertain"},
    {"retry_safe": False}, {"error_code": "OTHER_CONFLICT"},
    {"success": True}, {"ok": True}, {"contract_version": 2},
])
def test_other_preview_failures_are_never_retried(monkeypatch, changes):
    failure = _conflict(**changes)
    client, call = _client(monkeypatch, failure)
    assert client.call("preview_attachment", doc_name="LiveAttach") is failure
    assert call.call_count == 1


def test_other_tools_are_never_retried(monkeypatch):
    failure = _conflict()
    client, call = _client(monkeypatch, failure)
    assert client.call("create_datum_plane", doc_name="LiveAttach") is failure
    assert call.call_count == 1
