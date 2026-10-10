"""Live checks for the defects the eleventh agent stress run reported."""

from __future__ import annotations

import re

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


def test_preview_attachment_reports_the_face_offset(mcp, gui_log):
    """Distance is the face-to-plane offset, and the support names that face."""

    assert_ok(mcp.call("create_document", name="LiveAttach"))
    assert_ok(mcp.call("body_create", doc_name="LiveAttach", body_name="Body"))
    assert_ok(mcp.call(
        "sketch_create",
        doc_name="LiveAttach",
        sketch_name="Sk",
        body_name="Body",
        attach_to="XY_Plane",
    ))
    assert_ok(mcp.call(
        "sketch_add_rectangle",
        doc_name="LiveAttach",
        sketch_name="Sk",
        x1=0, y1=0, x2=40, y2=20,
    ))
    assert_ok(mcp.call(
        "pad_feature",
        doc_name="LiveAttach",
        sketch_name="Sk",
        pad_name="Pad",
        length=30,
        body_name="Body",
    ))
    found = _payload(assert_ok(mcp.call(
        "find_faces",
        doc_name="LiveAttach",
        object_name="Pad",
        type="Plane",
        normal_approx={"x": 0, "y": 0, "z": 1},
    )))
    face = found["results"][0]
    assert face["global_center"]["z"] == pytest.approx(30.0)
    sub = str(face["sub"])
    assert_ok(mcp.call(
        "create_datum_plane",
        doc_name="LiveAttach",
        plane_name="OffsetPlane",
        body_name="Body",
        mode="offset_from_face",
        face_a=f"Pad:{sub}",
        offset_along_normal=[20],
    ))
    preview = _payload(assert_ok(mcp.call(
        "preview_attachment",
        doc_name="LiveAttach",
        datum_name="OffsetPlane",
    )))
    assert preview["distance"] == pytest.approx(20.0)
    assert preview["diff"]["signed_distance_mm"] == pytest.approx(20.0)
    assert preview["diff"]["angle_deg"] == pytest.approx(0.0, abs=1.0)
    entry = next(item for item in preview["support"] if item.get("object") == "Pad")
    assert entry["sub"] == sub
    assert entry["center"]["z"] == pytest.approx(30.0)
    assert entry["normal"]["z"] == pytest.approx(1.0, abs=1e-6)
    assert_ok(mcp.call("close_document", doc_name="LiveAttach"))
    assert_clean(gui_log)


def test_move_into_a_part_reports_linked_companions(mcp, gui_log):
    """A Part move reports the other objects FreeCAD pulls into the group."""

    assert_ok(mcp.call("create_document", name="LiveMove"))
    assert_ok(mcp.call(
        "create_object",
        doc_name="LiveMove",
        obj_type="Part::Box",
        obj_name="Box",
        obj_properties={"Length": 10, "Width": 10, "Height": 10},
    ))
    assert_ok(mcp.call(
        "create_object",
        doc_name="LiveMove",
        obj_type="Part::Box",
        obj_name="Cyl",
        obj_properties={"Placement": {"Base": {"x": 20, "y": 0, "z": 0}}},
    ))
    assert_ok(mcp.call(
        "boolean_union",
        doc_name="LiveMove",
        shape1="Box",
        shape2="Cyl",
        result_name="Fused",
    ))
    assert_ok(mcp.call(
        "create_object",
        doc_name="LiveMove",
        obj_type="App::Part",
        obj_name="Part",
    ))
    moved = _payload(assert_ok(mcp.call(
        "move_object",
        doc_name="LiveMove",
        obj_name="Fused",
        target_container="Part",
    )))
    assert moved["object_name"] == "Fused"
    assert set(moved["also_moved"]) >= {"Box", "Cyl"}
    assert "Fused" not in moved["also_moved"]
    assert_ok(mcp.call("close_document", doc_name="LiveMove"))
    assert_clean(gui_log)


def test_a_disjoint_intersection_is_rolled_back(mcp, gui_log):
    """Two solids that do not overlap must not leave an empty Common behind."""

    assert_ok(mcp.call("create_document", name="LiveBool"))
    assert_ok(mcp.call(
        "create_object",
        doc_name="LiveBool",
        obj_type="Part::Box",
        obj_name="Box",
        obj_properties={"Length": 10, "Width": 10, "Height": 10},
    ))
    assert_ok(mcp.call(
        "create_object",
        doc_name="LiveBool",
        obj_type="Part::Box",
        obj_name="Other",
        obj_properties={"Placement": {"Base": {"x": 50}}},
    ))
    failed = mcp.call(
        "boolean_intersection",
        doc_name="LiveBool",
        shape1="Box",
        shape2="Other",
        result_name="Common",
    )
    assert not failed.ok, failed.text[:400]
    assert "empty" in failed.text.lower()
    listed = _payload(assert_ok(mcp.call("get_objects", doc_name="LiveBool")))
    assert "Common" not in {item["Name"] for item in listed["objects"]}
    assert_ok(mcp.call("close_document", doc_name="LiveBool"))
    assert_clean(gui_log)


def test_unknown_selection_names_the_object(mcp, gui_log):
    """An unknown name fails in the tool result and does not clear the selection."""

    assert_ok(mcp.call("create_document", name="LiveSelect"))
    assert_ok(mcp.call(
        "create_object",
        doc_name="LiveSelect",
        obj_type="Part::Box",
        obj_name="Box",
    ))
    assert_ok(mcp.call(
        "select_subshapes",
        doc_name="LiveSelect",
        selections=["Box"],
        clear=True,
    ))
    failed = mcp.call(
        "select_subshapes",
        doc_name="LiveSelect",
        selections=["MissingBox"],
        clear=True,
    )
    assert not failed.ok, failed.text[:400]
    assert "MissingBox" in failed.text
    assert "RPC failed" not in failed.text
    selected = _payload(assert_ok(mcp.call("get_selection")))
    names = [item.get("object") for item in selected.get("selection", [])]
    assert "Box" in names
    assert_ok(mcp.call("close_document", doc_name="LiveSelect"))
    assert_clean(gui_log)


def test_sweep_frenet_uses_the_pipe_mode(mcp, gui_log):
    """frenet=true selects AdditivePipe Mode Frenet."""

    assert_ok(mcp.call("create_document", name="LiveSweep"))
    assert_ok(mcp.call("body_create", doc_name="LiveSweep", body_name="SweepBody"))
    assert_ok(mcp.call(
        "sketch_create",
        doc_name="LiveSweep",
        sketch_name="SweepProfile",
        body_name="SweepBody",
        attach_to="XY_Plane",
    ))
    assert_ok(mcp.call(
        "sketch_create",
        doc_name="LiveSweep",
        sketch_name="SweepPath",
        body_name="SweepBody",
        attach_to="XZ_Plane",
    ))
    assert_ok(mcp.call(
        "sketch_add_circle",
        doc_name="LiveSweep",
        sketch_name="SweepProfile",
        cx=0, cy=0, radius=3,
    ))
    assert_ok(mcp.call(
        "sketch_add_line",
        doc_name="LiveSweep",
        sketch_name="SweepPath",
        x1=0, y1=0, x2=0, y2=40,
    ))
    assert_ok(mcp.call(
        "sweep_feature",
        doc_name="LiveSweep",
        profile_sketch="SweepProfile",
        path_sketch="SweepPath",
        sweep_name="Sweep",
        body_name="SweepBody",
        frenet=True,
    ))
    printed = assert_ok(mcp.call(
        "execute_code",
        document="LiveSweep",
        execution_mode="worker",
        read_only=True,
        code=(
            "import FreeCAD as App\n"
            "pipe = App.getDocument('LiveSweep').getObject('Sweep')\n"
            "print(pipe.Mode)\n"
        ),
    ))
    match = re.search(r"Output:\s*(.+)", printed.text)
    assert match, printed.text[:600]
    assert match.group(1).strip() == "Frenet"
    assert_ok(mcp.call("close_document", doc_name="LiveSweep"))
    assert_clean(gui_log)


def test_recompute_reports_a_missing_expression_source(mcp, gui_log):
    """Closing the expression source must surface that document in the tool error."""

    assert_ok(mcp.call("create_document", name="QASrc"))
    assert_ok(mcp.call(
        "create_object",
        doc_name="QASrc",
        obj_type="Part::Box",
        obj_name="SrcBox",
        obj_properties={"Length": 12, "Width": 10, "Height": 8},
    ))
    assert_ok(mcp.call("create_document", name="QADst"))
    assert_ok(mcp.call(
        "create_object",
        doc_name="QADst",
        obj_type="Part::Box",
        obj_name="Box",
        obj_properties={"Length": 10, "Width": 10, "Height": 10},
    ))
    assert_ok(mcp.call(
        "set_expression",
        doc_name="QADst",
        object_name="Box",
        prop_path="Length",
        expression="QASrc#SrcBox.Length",
    ))
    assert_ok(mcp.call("close_document", doc_name="QASrc"))
    failed = mcp.call("recompute_document", doc_name="QADst")
    assert not failed.ok, failed.text[:600]
    assert "QASrc" in failed.text
    assert "Box.Length" in failed.text
    assert_ok(mcp.call("close_document", doc_name="QADst"))
    assert_clean(
        gui_log,
        r"QASrc",
        r"property binding",
        r"Failed to recompute",
        r"postflight",
    )


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
