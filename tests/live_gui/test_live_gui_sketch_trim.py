"""Whole-element trim regression from the round 13 modeling scenario."""

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui


def _line(mcp, doc, **coords):
    assert_ok(mcp.call("sketch_add_line", doc_name=doc, sketch_name="TrimBug", **coords))


def _sketch(mcp, doc):
    assert_ok(mcp.call("create_document", name=doc))
    assert_ok(mcp.call("body_create", doc_name=doc, body_name="Body"))
    assert_ok(mcp.call("sketch_create", doc_name=doc, sketch_name="TrimBug",
                       body_name="Body", attach_to="XY_Plane"))
    _line(mcp, doc, x1=0, y1=5, x2=40, y2=5)


def _geometry(mcp, doc):
    return _payload(assert_ok(mcp.call("get_sketch_geometry", doc_name=doc,
                                      sketch_name="TrimBug")))


def test_trim_at_intersection_keeps_the_remaining_segment(mcp, gui_log):
    doc = "R13TrimIntersection"
    _sketch(mcp, doc)
    _line(mcp, doc, x1=10, y1=1, x2=10, y2=10)
    before = _geometry(mcp, doc)
    result = _payload(assert_ok(mcp.call("sketch_trim", doc_name=doc, sketch_name="TrimBug",
                                        geo_index=0, point_x=20, point_y=5)))
    after = _geometry(mcp, doc)
    assert result["committed"] is True
    assert after["geometry_count"] == before["geometry_count"] == 2
    assert after["geometry"] != before["geometry"]
    assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)


def test_trim_without_intersection_refuses_whole_element_deletion(mcp, gui_log):
    doc = "R13TrimNoIntersection"
    _sketch(mcp, doc)
    before = _geometry(mcp, doc)
    result = mcp.call("sketch_trim", doc_name=doc, sketch_name="TrimBug",
                      geo_index=0, point_x=20, point_y=5)
    after = _geometry(mcp, doc)
    assert result.is_error is True, result.text
    payload = _payload(result)
    assert payload["error_code"] == "TRIM_NO_INTERSECTION", result.text
    assert payload["committed"] is False
    assert payload["rollback_succeeded"] is True
    assert after == before
    assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)
