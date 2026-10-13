"""Appearance persistence regression from the round 13 Pad scenario."""

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload
from tests.live_gui.test_live_gui_stress import _part_body

pytestmark = pytest.mark.live_gui


def _view(mcp, doc):
    rows = _payload(assert_ok(mcp.call("get_objects", doc_name=doc, include_view=True)))
    return next(row["ViewObject"] for row in rows["objects"] if row["Name"] == "Pad")


def _red_pad(mcp, doc):
    _part_body(mcp, doc)
    assert_ok(mcp.call("set_color", doc_name=doc, obj_name="Pad", r=1, g=0, b=0,
                       transparency=0))
    assert _view(mcp, doc)["ShapeColor"] == pytest.approx([1, 0, 0, 1])


def test_set_color_keeps_pad_color_after_view_refresh(mcp, gui_log):
    doc = "R13AppearanceRefresh"
    _red_pad(mcp, doc)
    assert_ok(mcp.call("refresh_view", focus_object="Pad", fit=True, capture=False,
                       view_name="Isometric"))
    assert _view(mcp, doc)["ShapeColor"] == pytest.approx([1, 0, 0, 1])
    assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)


def test_pad_color_survives_hide_recompute_show(mcp, gui_log):
    doc = "R13AppearanceHideShow"
    _red_pad(mcp, doc)
    for tool, args in [
        ("edit_object", dict(obj_name="Pad", obj_properties={"Visibility": False})),
        ("recompute_document", {}),
        ("edit_object", dict(obj_name="Pad", obj_properties={"Visibility": True})),
    ]:
        assert_ok(mcp.call(tool, doc_name=doc, **args))
        view = _view(mcp, doc)
        assert view["ShapeColor"] == pytest.approx([1, 0, 0, 1]), (tool, view)
    assert_ok(mcp.call("refresh_view", focus_object="Pad", fit=True, capture=False,
                       view_name="Isometric"))
    assert _view(mcp, doc)["ShapeColor"] == pytest.approx([1, 0, 0, 1])
    assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)
