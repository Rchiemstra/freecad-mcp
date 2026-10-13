"""Pad ownership regressions from the round 13 live GUI stress run."""

from __future__ import annotations

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui


def _rectangle(mcp, doc, sketch, body=None):
    args = dict(doc_name=doc, sketch_name=sketch, attach_to="XY_Plane")
    if body is not None:
        args["body_name"] = body
    assert_ok(mcp.call("sketch_create", **args))
    assert_ok(mcp.call("sketch_add_rectangle", doc_name=doc, sketch_name=sketch,
                       x1=0, y1=0, x2=12, y2=12))


def _healthy_pad(mcp, doc):
    _rectangle(mcp, doc, "OwnedSketch", "Body")
    result = assert_ok(mcp.call("pad_feature", doc_name=doc, sketch_name="OwnedSketch",
                                pad_name="OwnedPad", length=5, body_name="Body", strict=True))
    assert _payload(result)["committed"] is True, result.text
    volume = _payload(assert_ok(mcp.call("measure_volume", doc_name=doc, obj_name="OwnedPad")))
    assert volume["volume_mm3"] == pytest.approx(720)


def test_owning_body_pad_keeps_gui_running(mcp, gui_log):
    doc = "R13OwnedPad"
    assert_ok(mcp.call("create_document", name=doc))
    assert_ok(mcp.call("body_create", doc_name=doc, body_name="Body"))
    _healthy_pad(mcp, doc)
    assert_ok(mcp.call("list_documents"))
    assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)


def test_orphan_pad_is_rejected_and_gui_stays_usable(mcp, gui_log):
    doc = "R13OrphanPad"
    assert_ok(mcp.call("create_document", name=doc))
    assert_ok(mcp.call("body_create", doc_name=doc, body_name="Body"))
    # Omitting body_name creates a document-level sketch, even though its
    # attachment support is the Body's origin plane.
    _rectangle(mcp, doc, "OrphanSketch")
    before = _payload(assert_ok(mcp.call("get_document_tree", doc_name=doc, max_depth=3)))
    assert {row["Name"] for row in before["roots"]} == {"Body", "OrphanSketch"}

    result = mcp.call("pad_feature", doc_name=doc, sketch_name="OrphanSketch",
                      pad_name="OrphanPad", length=5, body_name="Body", strict=True)
    # Check a real FreeCAD read immediately after the Pad call, including on
    # the unfixed version; a transport error cannot stand in for a refusal.
    after = _payload(assert_ok(mcp.call("get_document_tree", doc_name=doc, max_depth=3)))
    assert result.is_error is True, result.text
    payload = _payload(result)
    for key, expected in {
        "ok": False, "success": False, "error_code": "SKETCH_NOT_IN_BODY",
        "outcome": "rejected", "committed": False, "rollback_succeeded": True,
        "native_status": "ApplyFailed",
    }.items():
        assert payload[key] == expected, result.text
    assert after == before
    # The same GUI session must still support an ordinary owning-Body Pad.
    _healthy_pad(mcp, doc)
    assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)
