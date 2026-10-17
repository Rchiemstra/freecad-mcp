"""Deterministic regressions for failure recovery in the shared GUI session."""

from contextlib import contextmanager

import pytest

from tests.live_gui import conftest, test_live_gui_round11, test_live_gui_round12
from tests.live_gui._support import ToolResult, assert_clean, assert_ok

pytestmark = pytest.mark.live_gui

_CONFLICT = "one or more semantic revisions changed before commit"


class _FailPreview:
    def __init__(self, client):
        self.client = client
        self.calls = 0

    def call(self, tool, **args):
        if tool == "preview_attachment":
            self.calls += 1
            return ToolResult(tool, True, _CONFLICT, {
                "success": False, "ok": False, "outcome": "rejected",
                "committed": False, "retry_safe": False,
                "error_code": "NATIVE_COMPATIBILITY_MUTATION_REJECTED",
                "native_status": "Conflict", "native_message": _CONFLICT,
                "error": _CONFLICT,
            })
        return self.client.call(tool, **args)


def test_round11_failure_closes_liveattach(mcp, gui_log):
    failing = _FailPreview(mcp)
    with pytest.raises(AssertionError, match=_CONFLICT):
        test_live_gui_round11.test_preview_attachment_reports_the_face_offset(failing, gui_log)
    assert "LiveAttach" not in assert_ok(mcp.call("list_documents")).text
    assert_clean(gui_log)


def test_mcp_fixture_unwinds_failed_test_without_retiring_session(
    mcp, live_gui, _live_gui_session, request, gui_log,
):
    # Exercise the actual fixture's failure finalizer with the real GUI/client.
    fixture = contextmanager(conftest.mcp.__wrapped__)
    with pytest.raises(AssertionError, match="forced test failure"):
        with fixture(live_gui, _live_gui_session, request) as client:
            assert_ok(client.call("create_document", name="CleanupFailure"))
            raise AssertionError("forced test failure")
    assert _live_gui_session.client is mcp
    assert _live_gui_session.gui is live_gui
    assert "CleanupFailure" not in assert_ok(mcp.call("list_documents")).text
    assert_ok(mcp.call("get_report_view"))
    assert_clean(gui_log)


def test_leaked_liveattach_before_modal_does_not_poison_next_request(mcp, gui_log):
    # Reproduce S-1 independently of native revision timing.
    if "LiveAttach" not in assert_ok(mcp.call("list_documents")).text:
        assert_ok(mcp.call("create_document", name="LiveAttach"))
    test_live_gui_round12.test_modal_dialog_is_reported_without_dispatching_gui_work(mcp, gui_log)
    assert "LiveAttach" not in assert_ok(mcp.call("list_documents")).text
    assert_ok(mcp.call("get_report_view"))
    assert_clean(gui_log)


def test_modal_setup_rejection_still_closes_dialog(mcp, gui_log):
    class BlockedSetup:
        def call(self, tool, **args):
            result = mcp.call(tool, **args)
            if tool == "execute_code" and "Round 12 modal" in args.get("code", ""):
                # The real setup has shown the dialog and armed its Qt timer.
                # Model a postflight rejection, before the caller's assertions.
                assert_ok(result)
                return ToolResult(tool, True, "GUI_BLOCKED_BY_MODAL_DIALOG", {
                    "success": False, "error_code": "GUI_BLOCKED_BY_MODAL_DIALOG",
                })
            return result

    with pytest.raises(AssertionError, match="GUI_BLOCKED_BY_MODAL_DIALOG"):
        test_live_gui_round12.test_modal_dialog_is_reported_without_dispatching_gui_work(
            BlockedSetup(), gui_log,
        )
    assert_ok(mcp.call("get_report_view"))
    assert_clean(gui_log)


def test_request_after_cleanup_regressions(mcp, gui_log):
    """A poisoned modal session must fail this following scenario too."""
    assert_ok(mcp.call("get_report_view"))
    assert_clean(gui_log)
