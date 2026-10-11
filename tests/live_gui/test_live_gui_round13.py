"""Round 13: world-shape summaries must reach the real MCP client intact."""

from __future__ import annotations

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui


def _box(mcp, document, **properties):
    assert_ok(mcp.call(
        "create_object", doc_name=document, obj_name="Box", obj_type="Part::Box",
        obj_properties={"Length": 10, "Width": 10, "Height": 10, **properties},
    ))


def test_box_center_of_mass_geometry_happy_path(mcp, gui_log):
    document = "R13CenterHappy"
    assert_ok(mcp.call("create_document", name=document))
    try:
        _box(mcp, document)
        center = _payload(assert_ok(mcp.call("center_of_mass", doc_name=document, obj_name="Box")))
        assert [center[axis] for axis in ("x", "y", "z")] == pytest.approx([5, 5, 5])
    finally:
        assert_ok(mcp.call("close_document", doc_name=document))
    assert_clean(gui_log)


@pytest.mark.parametrize("case", ["plain", "nested", "link"])
def test_global_shape_box_summary_has_world_center(mcp, gui_log, case):
    """A box's generic world-shape copy must carry a usable COM."""
    document = "R13Global" + case.title()
    assert_ok(mcp.call("create_document", name=document))
    try:
        target = "Box"
        offset = 0
        if case == "nested":
            assert_ok(mcp.call("create_part_container", doc_name=document, part_name="Part"))
            assert_ok(mcp.call(
                "edit_object", doc_name=document, obj_name="Part",
                obj_properties={"Placement": {"Base": {"x": 100, "y": 0, "z": 0}}},
            ))
            _box(mcp, document, Placement={"Base": {"x": 20, "y": 0, "z": 0}})
            assert_ok(mcp.call("move_object", doc_name=document, obj_name="Box", target_container="Part"))
            offset = 120
        else:
            _box(mcp, document)
            if case == "link":
                assert_ok(mcp.call(
                    "create_object", doc_name=document, obj_name="Link", obj_type="App::Link",
                    obj_properties={"LinkedObject": "Box"},
                ))
                target = "Link"

        summary = _payload(assert_ok(mcp.call("get_global_shape", doc_name=document, obj_name=target)))
        assert summary["outcome"] == "observed"
        assert summary["frame"] == "world"
        assert summary["object"] == target
        assert summary["volume_mm3"] == pytest.approx(1000)
        assert summary["area_mm2"] == pytest.approx(600)
        assert summary["center_of_mass"] == pytest.approx([offset + 5, 5, 5])
        assert (summary["solids"], summary["faces"], summary["edges"]) == (1, 6, 12)
        assert [summary["bbox"][key] for key in ("xmin", "ymin", "zmin", "xmax", "ymax", "zmax")] == pytest.approx(
            [offset, 0, 0, offset + 10, 10, 10],
        )
    finally:
        assert_ok(mcp.call("close_document", doc_name=document))
    assert_clean(gui_log)


def test_global_shape_single_edge_has_world_center(mcp, gui_log):
    document = "R13GlobalLine"
    assert_ok(mcp.call("create_document", name=document))
    try:
        assert_ok(mcp.call(
            "create_object", doc_name=document, obj_name="Line", obj_type="Part::Line",
            obj_properties={"X2": 0, "Y2": 100, "Z2": 0},
        ))
        summary = _payload(assert_ok(mcp.call("get_global_shape", doc_name=document, obj_name="Line")))
        assert summary["outcome"] == "observed"
        assert summary["center_of_mass"] == pytest.approx([0, 50, 0])
        assert summary["volume_mm3"] == pytest.approx(0)
        assert summary["area_mm2"] == pytest.approx(0)
        assert (summary["solids"], summary["faces"], summary["edges"]) == (0, 0, 1)
        assert [summary["bbox"][key] for key in ("xmin", "ymin", "zmin", "xmax", "ymax", "zmax")] == pytest.approx(
            [0, 0, 0, 0, 100, 0],
        )
    finally:
        assert_ok(mcp.call("close_document", doc_name=document))
    assert_clean(gui_log)
