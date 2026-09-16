"""The GUI-only pause gate must not create a remote resume surface."""

from __future__ import annotations

from pathlib import Path

import pytest

from addon.FreeCADMCP import automation_pause

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_pause_state():
    automation_pause._paused = False
    automation_pause._active.clear()
    automation_pause._last_finished = None
    yield
    automation_pause._paused = False
    automation_pause._active.clear()
    automation_pause._last_finished = None


def test_pause_after_current_allows_admitted_work_then_refuses_new_writes():
    admitted = automation_pause.admit_remote_write("pad_feature", ("Model",))
    assert admitted["success"] is True

    status = automation_pause.request_local_pause_after_current()
    assert status["pause_after_current"] is True
    assert status["current_operation"] == {
        "method": "pad_feature",
        "documents": ("Model",),
    }
    refused = automation_pause.admit_remote_write("pocket_feature", ("Model",))
    assert refused["error_code"] == "AUTOMATION_PAUSED"

    automation_pause.finish_remote_write(admitted["token"])
    assert automation_pause.status()["paused"] is True
    assert automation_pause.status()["current_operation"] is None
    assert automation_pause.status()["last_operation"] == {
        "method": "pad_feature",
        "documents": ("Model",),
    }


def test_remote_rpc_cannot_resume_local_pause():
    source = (
        Path(__file__).parents[1]
        / "addon"
        / "FreeCADMCP"
        / "rpc_server"
        / "rpc_server_ops"
        / "facade_bindings.py"
    ).read_text(encoding="utf-8")

    assert "resume_local_agent_writes" not in source
    assert "request_local_pause_after_current" not in source
