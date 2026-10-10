"""Live checks for the defects the eleventh agent stress run reported."""

from __future__ import annotations

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui


def _view_row(mcp, doc_name: str, obj_name: str) -> dict:
    listed = _payload(assert_ok(mcp.call(
        "get_objects",
        doc_name=doc_name,
        include_view=True,
    )))
    return next(item for item in listed["objects"] if item["Name"] == obj_name)


def test_viewobject_color_and_visibility_apply_after_the_app_commit(mcp, gui_log):
    """The documented ViewObject dict is applied on the GUI thread."""

    assert_ok(mcp.call("create_document", name="LiveViewProps"))
    assert_ok(mcp.call(
        "create_object",
        doc_name="LiveViewProps",
        obj_type="Part::Box",
        obj_name="Box",
        obj_properties={
            "Length": 10,
            "Width": 10,
            "Height": 10,
            "ViewObject": {"ShapeColor": [1, 0, 0, 1]},
        },
    ))
    color = _view_row(mcp, "LiveViewProps", "Box")["ViewObject"]["ShapeColor"]
    assert color[0] > 0.9
    assert color[1] < 0.1
    assert color[2] < 0.1

    assert_ok(mcp.call(
        "edit_object",
        doc_name="LiveViewProps",
        obj_name="Box",
        obj_properties={"ViewObject": {"Visibility": False}},
    ))
    view = _view_row(mcp, "LiveViewProps", "Box")["ViewObject"]
    assert view["Visibility"] is False

    assert_ok(mcp.call("close_document", doc_name="LiveViewProps"))
    assert_clean(gui_log)


def test_an_empty_document_listing_survives_a_missing_screenshot(mcp, gui_log):
    """get_objects must return the empty page when the view has nothing to frame."""

    assert_ok(mcp.call("create_document", name="LiveEmptyRead"))
    listed = _payload(
        assert_ok(mcp.call("get_objects", doc_name="LiveEmptyRead", page_size=10))
    )
    assert listed["objects"] == []
    warning = listed.get("screenshot_warning")
    if warning is not None:
        assert "Screenshot unavailable" in warning
    assert_ok(mcp.call("close_document", doc_name="LiveEmptyRead"))
    assert_clean(gui_log)
