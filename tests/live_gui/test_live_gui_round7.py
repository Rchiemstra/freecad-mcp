"""Live checks for the defects the seventh agent stress run reported."""

from __future__ import annotations

import time
import zipfile

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload, _rejected
from tests.live_gui.test_live_gui_stress import _part_body

pytestmark = pytest.mark.live_gui


def test_a_failed_link_array_edit_leaves_the_document_usable(mcp, gui_log):
    """ElementCount + ShowElement + read-only ElementList poisoned the
    rollback; every later mutation of the document was refused."""

    assert_ok(mcp.call("create_document", name="LiveLinkArr"))
    assert_ok(mcp.call("create_object", doc_name="LiveLinkArr", obj_type="Part::Box",
                       obj_name="Box"))
    assert_ok(mcp.call("create_object", doc_name="LiveLinkArr", obj_type="App::Link",
                       obj_name="Link", obj_properties={"LinkedObject": "Box"}))

    _rejected(mcp.call("edit_object", doc_name="LiveLinkArr", obj_name="Link",
                       obj_properties={"ElementCount": 5, "ShowElement": False,
                                       "ElementList": []}), "'ElementList'")
    assert_ok(mcp.call("edit_object", doc_name="LiveLinkArr", obj_name="Link",
                       obj_properties={"ElementCount": 3}))
    assert_ok(mcp.call("create_object", doc_name="LiveLinkArr", obj_type="Part::Box",
                       obj_name="After"))
    assert_ok(mcp.call("close_document", doc_name="LiveLinkArr"))
    assert_clean(gui_log)


def test_reload_refuses_unsaved_changes_and_reports_the_new_name(mcp, gui_log, live_gui):
    destination = live_gui.workdir / "reloaded_part.FCStd"
    assert_ok(mcp.call("create_document", name="LiveReload"))
    assert_ok(mcp.call("create_object", doc_name="LiveReload", obj_type="Part::Box",
                       obj_name="Box"))
    assert_ok(mcp.call("save_document_as", selector={"document_name": "LiveReload"},
                       destination=str(destination)))
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not zipfile.is_zipfile(destination):
        time.sleep(0.2)
    assert_ok(mcp.call("edit_object", doc_name="LiveReload", obj_name="Box",
                       obj_properties={"Length": 25}))

    _rejected(mcp.call("reload_document", doc_name="LiveReload"), "unsaved changes")
    assert_ok(mcp.call("save_document", selector={"document_name": "LiveReload"}))
    reloaded = _payload(assert_ok(mcp.call("reload_document", doc_name="LiveReload")))

    assert reloaded["previous_name"] == "LiveReload"
    assert reloaded["document_name"] == "reloaded_part"
    assert_ok(mcp.call("close_document", doc_name="reloaded_part"))
    assert_clean(gui_log)


def test_sketch_tools_report_and_keep_their_shape(mcp, gui_log):
    _part_body(mcp, "LiveSkDiag")
    assert_ok(mcp.call("sketch_create", doc_name="LiveSkDiag", sketch_name="Sk2",
                       body_name="Body"))
    assert_ok(mcp.call("sketch_add_rectangle", doc_name="LiveSkDiag", sketch_name="Sk2",
                       x1=0, y1=0, x2=8, y2=4))
    # Dimensioning one edge used to pull the rectangle open.
    assert_ok(mcp.call("sketch_constrain_distance", doc_name="LiveSkDiag", sketch_name="Sk2",
                       geo=0, value=12, name="W"))

    diagnostics = _payload(assert_ok(mcp.call("get_sketch_diagnostics", doc_name="LiveSkDiag",
                                              sketch_name="Sk2")))
    assert diagnostics["is_closed"] is True
    assert "dof" in diagnostics and "fully_constrained" in diagnostics

    assert_ok(mcp.call("spreadsheet_create", doc_name="LiveSkDiag", sheet_name="Dims"))
    assert_ok(mcp.call("spreadsheet_set_cells", doc_name="LiveSkDiag", sheet_name="Dims",
                       cells=[{"address": "A1", "value": 12, "alias": "Wd"}]))
    assert_ok(mcp.call("set_expression", doc_name="LiveSkDiag", object_name="Sk2",
                       prop_path=".Constraints.W", expression="<<Dims>>.Wd"))
    _rejected(mcp.call("sketch_edit_constraint", doc_name="LiveSkDiag", sketch_name="Sk2",
                       name="W", value=14), "driven by the expression")
    cells = _payload(assert_ok(mcp.call("spreadsheet_get_cells", doc_name="LiveSkDiag",
                                        sheet_name="Dims", addresses=["B7"])))
    assert cells["cells"][0]["value"] is None and "value_error" not in cells["cells"][0]
    assert_ok(mcp.call("close_document", doc_name="LiveSkDiag"))
    assert_clean(gui_log)


def test_a_binder_on_a_missing_face_is_refused(mcp, gui_log):
    _part_body(mcp, "LiveBinder")

    _rejected(mcp.call("create_subshape_binder", doc_name="LiveBinder", binder_name="B",
                       source_object="Pad", sub_elements=["Face999"], target_body="Body"),
              "Pad.Face999")
    objects = assert_ok(mcp.call("get_objects", doc_name="LiveBinder"))
    assert '"B"' not in objects.text
    assert_ok(mcp.call("close_document", doc_name="LiveBinder"))
    assert_clean(gui_log)
