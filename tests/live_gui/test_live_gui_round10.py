"""Live checks for the defects the tenth agent stress run reported."""

from __future__ import annotations

import time
import zipfile

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload, _rejected

pytestmark = pytest.mark.live_gui


def test_reload_of_a_non_zip_keeps_the_open_document(mcp, gui_log, live_gui):
    """A file that only starts with a zip header must not close the document."""

    destination = live_gui.workdir / "not_a_zip.FCStd"
    assert_ok(mcp.call("create_document", name="LiveBadReload"))
    assert_ok(mcp.call(
        "create_object",
        doc_name="LiveBadReload",
        obj_type="Part::Box",
        obj_name="Box",
    ))
    assert_ok(mcp.call(
        "save_document_as",
        selector={"document_name": "LiveBadReload"},
        destination=str(destination),
    ))
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not zipfile.is_zipfile(destination):
        time.sleep(0.2)
    destination.write_bytes(b"PK\x03\x04not-a-valid-fcstd")

    _rejected(mcp.call("reload_document", doc_name="LiveBadReload"), "not a FreeCAD document")
    listed = _payload(assert_ok(mcp.call("get_objects", doc_name="LiveBadReload")))
    assert {item["Name"] for item in listed["objects"]} >= {"Box"}
    assert_ok(mcp.call("close_document", doc_name="LiveBadReload"))
    assert_clean(gui_log)


def test_save_as_refuses_an_existing_destination(mcp, gui_log, live_gui):
    """overwrite false must not replace a file Save As already adopted."""

    destination = live_gui.workdir / "no_clobber.FCStd"
    assert_ok(mcp.call("create_document", name="LiveNoClobber"))
    assert_ok(mcp.call(
        "create_object",
        doc_name="LiveNoClobber",
        obj_type="Part::Box",
        obj_name="Box",
    ))
    assert_ok(mcp.call(
        "save_document_as",
        selector={"document_name": "LiveNoClobber"},
        destination=str(destination),
        overwrite=False,
    ))
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not zipfile.is_zipfile(destination):
        time.sleep(0.2)
    original = destination.read_bytes()

    _rejected(
        mcp.call(
            "save_document_as",
            selector={"document_name": "LiveNoClobber"},
            destination=str(destination),
            overwrite=False,
        ),
        "overwrite=False",
    )
    assert destination.read_bytes() == original
    assert_ok(mcp.call(
        "save_document_as",
        selector={"document_name": "LiveNoClobber"},
        destination=str(destination),
        overwrite=True,
    ))
    assert_ok(mcp.call("close_document", doc_name="LiveNoClobber"))
    assert_clean(gui_log)


def test_gui_state_and_view_follow_the_active_document(mcp, gui_log):
    """activate_document must win over the document that was created last."""

    assert_ok(mcp.call("create_document", name="LiveViewA"))
    assert_ok(mcp.call(
        "create_object",
        doc_name="LiveViewA",
        obj_type="Part::Box",
        obj_name="BoxA",
    ))
    assert_ok(mcp.call("create_document", name="LiveViewB"))
    assert_ok(mcp.call(
        "create_object",
        doc_name="LiveViewB",
        obj_type="Part::Box",
        obj_name="BoxB",
    ))
    assert_ok(mcp.call("activate_document", doc_name="LiveViewA"))

    state = _payload(assert_ok(mcp.call("get_gui_state")))
    assert state["active_document"] == "LiveViewA"
    assert_ok(mcp.call("get_view", view_name="Isometric", focus_object="BoxA"))
    assert_ok(mcp.call("get_view", view_name="Isometric"))
    _rejected(
        mcp.call("get_view", view_name="Isometric", focus_object="BoxB"),
        "not present",
    )
    assert_ok(mcp.call(
        "get_view",
        view_name="Isometric",
        focus_object="BoxB",
        document="LiveViewB",
    ))
    assert_ok(mcp.call("close_document", doc_name="LiveViewA"))
    assert_ok(mcp.call("close_document", doc_name="LiveViewB"))
    assert_clean(gui_log)
