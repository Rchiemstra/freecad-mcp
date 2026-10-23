"""Authenticate a fresh GUI runtime after a full launcher restart."""

import json

import pytest

from tests.live_gui._support import GuiLog, assert_clean, assert_ok

pytestmark = pytest.mark.live_gui


def test_authenticated_startup_restart(_live_gui_session):
    session = _live_gui_session
    session.start()
    previous = json.loads(session.gui.manifest.read_text())
    session.close()
    session.start()
    current = json.loads(session.gui.manifest.read_text())
    assert current["expected_freecad_pid"] != previous["expected_freecad_pid"]
    assert current["expected_addon_runtime_id"] != previous["expected_addon_runtime_id"]
    log = GuiLog(session.gui.logs)
    assert_ok(session.client.call("get_report_view"))
    assert_clean(log)
