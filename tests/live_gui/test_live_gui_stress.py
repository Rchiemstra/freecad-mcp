"""Stress scenarios against a launched FreeCAD GUI through the real MCP server.

Each scenario passes only when every MCP call behaves and FreeCAD prints no new
warning or error. They came from live stress runs that found GUI-only defects
the unit layers could not see (a stray PySide2 breaking every mutation, undo
and redo binding, Coin scene-graph and camera-overflow errors, a self
referencing spreadsheet formula poisoning the document).
"""

from __future__ import annotations

import pytest

from tests.live_gui._support import assert_clean, assert_ok

pytestmark = pytest.mark.live_gui


def _part_body(mcp, doc: str, *, length: float = 5) -> None:
    assert_ok(mcp.call("create_document", name=doc))
    assert_ok(mcp.call("body_create", doc_name=doc, body_name="Body"))
    assert_ok(mcp.call("sketch_create", doc_name=doc, sketch_name="Sk", body_name="Body"))
    assert_ok(mcp.call("sketch_add_rectangle", doc_name=doc, sketch_name="Sk",
                       x1=0, y1=0, x2=20, y2=10))
    assert_ok(mcp.call("pad_feature", doc_name=doc, sketch_name="Sk", pad_name="Pad",
                       length=length, body_name="Body"))


def test_partdesign_flow_with_undo_redo_and_views(mcp, gui_log):
    _part_body(mcp, "LiveA")
    assert_ok(mcp.call("fillet_feature", doc_name="LiveA", base_feature="Pad",
                       fillet_name="Fillet", radius=1, body_name="Body"))
    assert_ok(mcp.call("set_color", doc_name="LiveA", obj_name="Pad", r=1, g=0, b=0))
    assert_ok(mcp.call("recompute_document", doc_name="LiveA"))
    for _ in range(3):
        assert_ok(mcp.call("undo", doc_name="LiveA"))
    for _ in range(3):
        assert_ok(mcp.call("redo", doc_name="LiveA"))
    assert_ok(mcp.call("sketch_create", doc_name="LiveA", sketch_name="Hole", body_name="Body"))
    assert_ok(mcp.call("sketch_add_circle", doc_name="LiveA", sketch_name="Hole",
                       cx=10, cy=5, radius=2))
    assert_ok(mcp.call("pocket_feature", doc_name="LiveA", sketch_name="Hole",
                       pocket_name="Pocket", length=3, body_name="Body"))
    assert_ok(mcp.call("refresh_view", fit=True))
    assert_ok(mcp.call("get_view", view_name="Isometric", width=320, height=240))
    refused = mcp.call("delete_object", doc_name="LiveA", obj_name="Fillet")
    assert not refused.ok
    assert "Refused to delete 'Fillet'" in refused.text and "Pocket" in refused.text
    objects = assert_ok(mcp.call("get_objects", doc_name="LiveA"))
    assert "Fillet" in objects.text
    assert_ok(mcp.call("close_document", doc_name="LiveA"))

    assert_clean(gui_log)


def test_two_documents_in_parallel(mcp, gui_log):
    for result in mcp.parallel([("create_document", {"name": "LivePA"}),
                                ("create_document", {"name": "LivePB"})]):
        assert_ok(result)
    for result in mcp.parallel([
        ("create_object", {"doc_name": "LivePA", "obj_type": "Part::Box", "obj_name": "B1"}),
        ("create_object", {"doc_name": "LivePB", "obj_type": "Part::Box", "obj_name": "B2"}),
        ("create_object", {"doc_name": "LivePA", "obj_type": "Part::Cylinder",
                           "obj_name": "C1", "obj_properties": {"Radius": 3, "Height": 20}}),
        ("create_object", {"doc_name": "LivePB", "obj_type": "Part::Sphere", "obj_name": "S1"}),
    ]):
        assert_ok(result)
    for result in mcp.parallel([
        ("boolean_union", {"doc_name": "LivePA", "shape1": "B1", "shape2": "C1",
                           "result_name": "U1"}),
        ("edit_object", {"doc_name": "LivePB", "obj_name": "B2",
                         "obj_properties": {"Height": 30}}),
        ("spreadsheet_create", {"doc_name": "LivePA", "sheet_name": "Sheet"}),
        ("measure_volume", {"doc_name": "LivePB", "obj_name": "S1"}),
    ]):
        assert_ok(result)
    for result in mcp.parallel([("get_object", {"doc_name": "LivePA", "obj_name": "U1"}),
                                ("get_object", {"doc_name": "LivePB", "obj_name": "B2"}),
                                ("undo", {"doc_name": "LivePA"}),
                                ("undo", {"doc_name": "LivePB"})]):
        assert_ok(result)
    for result in mcp.parallel([("close_document", {"doc_name": "LivePA"}),
                                ("close_document", {"doc_name": "LivePB"})]):
        assert_ok(result)

    assert_clean(gui_log)


def test_burst_of_parallel_creates_and_reads(mcp, gui_log):
    assert_ok(mcp.call("create_document", name="LiveBurst"))
    names = [f"Box{i}" for i in range(12)]
    for result in mcp.parallel(
        ("create_object", {"doc_name": "LiveBurst", "obj_type": "Part::Box", "obj_name": name,
                           "obj_properties": {"Length": 1 + index}})
        for index, name in enumerate(names)
    ):
        assert_ok(result)
    for result in mcp.parallel(
        ("get_object", {"doc_name": "LiveBurst", "obj_name": name}) for name in names
    ):
        assert_ok(result)
    assert_ok(mcp.call("close_document", doc_name="LiveBurst"))

    assert_clean(gui_log)


@pytest.mark.parametrize(
    ("tool", "args", "reason"),
    [
        ("body_create", {"doc_name": "NoSuchDoc", "body_name": "Body"}, "not found"),
        ("undo", {"doc_name": "NoSuchDoc"}, "not found"),
        ("create_document", {"name": "LiveInvalid"}, "already exists"),
        ("sketch_add_rectangle", {"doc_name": "LiveInvalid", "sketch_name": "Sk",
                                  "x1": 0, "y1": 0, "x2": 0, "y2": 0}, "points are equal"),
        ("pad_feature", {"doc_name": "LiveInvalid", "sketch_name": "Sk", "pad_name": "Zero",
                         "length": 0, "body_name": "Body"}, "greater than zero"),
        ("fillet_feature", {"doc_name": "LiveInvalid", "base_feature": "Pad",
                            "fillet_name": "F0", "radius": 0, "body_name": "Body"}, "radius"),
        ("sketch_add_circle", {"doc_name": "LiveInvalid", "sketch_name": "Sk",
                               "cx": 0, "cy": 0, "radius": 0}, "radius"),
    ],
)
def test_rejected_input_reports_its_reason(mcp, gui_log, tool, args, reason):
    """Rejections used to read "invalid contract response; requires reconciliation"."""

    if mcp.call("get_object", doc_name="LiveInvalid", obj_name="Pad").is_error:
        _part_body(mcp, "LiveInvalid")
        gui_log.reset()

    result = mcp.call(tool, **args)

    assert not result.ok
    assert "reconciliation" not in result.text
    assert reason in result.text.lower(), result.text[:600]
    assert_clean(gui_log)


def test_cyclic_spreadsheet_formula_leaves_document_usable(mcp, gui_log):
    assert_ok(mcp.call("create_document", name="LiveSheet"))
    assert_ok(mcp.call("spreadsheet_create", doc_name="LiveSheet", sheet_name="Dims"))

    cyclic = mcp.call("spreadsheet_set_cells", doc_name="LiveSheet", sheet_name="Dims",
                      cells=[{"address": "B1", "value": "=B1 + 1"}])
    assert not cyclic.ok
    assert "blocked restoration" not in cyclic.text

    assert_ok(mcp.call("spreadsheet_set_cells", doc_name="LiveSheet", sheet_name="Dims",
                       cells=[{"address": "A1", "value": "42"}]))
    assert_ok(mcp.call("close_document", doc_name="LiveSheet"))

    # FreeCAD reports the rejected recompute itself; nothing else may appear.
    assert_clean(gui_log, r"Cyclic dependency detected", r"Failed to recompute",
                 r"cells failed contains errors")


def test_deleting_the_tip_feature_keeps_the_body_solid(mcp, gui_log):
    """Deleting a Body's Tip through MCP used to leave the Body without a shape."""

    _part_body(mcp, "LiveTip", length=4)
    assert_ok(mcp.call("pad_feature", doc_name="LiveTip", sketch_name="Sk",
                       pad_name="PadDup", length=2, body_name="Body"))

    deleted = assert_ok(mcp.call("delete_object", doc_name="LiveTip", obj_name="PadDup"))

    assert deleted.payload["deleted"] == ["PadDup"]
    volume = assert_ok(mcp.call("measure_volume", doc_name="LiveTip", obj_name="Body"))
    assert volume.payload["volume_mm3"] == pytest.approx(20 * 10 * 4)
    validated = assert_ok(mcp.call("validate_geometry", doc_name="LiveTip", obj_name="Body"))
    assert validated.payload["check_ok"] is True
    assert_ok(mcp.call("close_document", doc_name="LiveTip"))

    assert_clean(gui_log)


def _crossing_lines(mcp, doc: str) -> None:
    assert_ok(mcp.call("create_document", name=doc))
    assert_ok(mcp.call("sketch_create", doc_name=doc, sketch_name="T"))
    assert_ok(mcp.call("sketch_add_line", doc_name=doc, sketch_name="T",
                       x1=-50, y1=0, x2=50, y2=0))
    assert_ok(mcp.call("sketch_add_line", doc_name=doc, sketch_name="T",
                       x1=0, y1=-40, x2=0, y2=40))


def test_failed_sketch_trim_keeps_freecad_running(mcp, gui_log):
    """OpenCASCADE's StdFail_NotDone from this trim used to abort FreeCAD."""

    _crossing_lines(mcp, "LiveTrim")
    assert_ok(mcp.call("sketch_trim", doc_name="LiveTrim", sketch_name="T",
                       geo_index=0, point_x=25, point_y=0))

    failed = mcp.call("sketch_trim", doc_name="LiveTrim", sketch_name="T",
                      geo_index=1, point_x=900, point_y=900)

    assert not failed.ok
    assert "Disconnected" not in failed.text
    assert_ok(mcp.call("list_documents"))
    assert_ok(mcp.call("sketch_trim", doc_name="LiveTrim", sketch_name="T",
                       geo_index=1, point_x=0, point_y=20))
    assert_ok(mcp.call("close_document", doc_name="LiveTrim"))
    assert_clean(gui_log)


def test_unsolvable_constraint_value_names_the_solver_not_the_index(mcp, gui_log):
    _crossing_lines(mcp, "LiveDatum")
    assert_ok(mcp.call("sketch_constrain_distance", doc_name="LiveDatum", sketch_name="T",
                       geo=0, value=100, name="Width"))

    failed = mcp.call("sketch_edit_constraint", doc_name="LiveDatum", sketch_name="T",
                      name="Width", value=-45)

    assert not failed.ok
    assert "Invalid constraint index" not in failed.text
    assert "Negative datum" in failed.text
    assert_ok(mcp.call("close_document", doc_name="LiveDatum"))
    assert_clean(gui_log)


def test_save_as_writes_a_thumbnail_without_warnings(mcp, gui_log, live_gui):
    """Async saves serialize off the GUI thread, where the thumbnail cannot be
    rendered: every save warned and new documents were saved without one."""

    import time
    import zipfile

    destination = live_gui.workdir / "thumbnail.FCStd"
    assert_ok(mcp.call("create_document", name="LiveThumb"))
    assert_ok(mcp.call("create_object", doc_name="LiveThumb", obj_type="Part::Box",
                       obj_name="Box"))

    assert_ok(mcp.call("save_document_as", selector={"document_name": "LiveThumb"},
                       destination=str(destination)))

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not zipfile.is_zipfile(destination):
        time.sleep(0.2)
    with zipfile.ZipFile(destination) as archive:
        png = archive.read("thumbnails/Thumbnail.png")
    # A rendered view at the default ThumbnailSize, not the app-icon fallback.
    assert int.from_bytes(png[16:20], "big") == 256
    assert not destination.with_name("thumbnail.FCStd.FreeCAD-save.lock").exists()
    assert_ok(mcp.call("close_document", doc_name="LiveThumb"))
    assert_clean(gui_log)


def test_restoring_a_snapshot_keeps_freecad_responsive(mcp, gui_log):
    """restore closes the document from an RPC worker thread. FreeCAD's GUI
    delete handler runs Python, and the worker kept the GIL while waiting for
    the GUI thread, so FreeCAD deadlocked and every later call timed out."""

    assert_ok(mcp.call("create_document", name="LiveRestore"))
    for name in ("BoxA", "BoxB"):
        assert_ok(mcp.call("create_object", doc_name="LiveRestore", obj_type="Part::Box",
                           obj_name=name))
    assert_ok(mcp.call("snapshot", doc_name="LiveRestore"))
    assert_ok(mcp.call("delete_object", doc_name="LiveRestore", obj_name="BoxB"))

    assert_ok(mcp.call("restore", doc_name="LiveRestore"))

    objects = assert_ok(mcp.call("get_objects", doc_name="LiveRestore"))
    assert "BoxB" in objects.text
    assert_ok(mcp.call("close_document", doc_name="LiveRestore"))
    assert_clean(gui_log)


def test_assembly_joints_can_be_created(mcp, gui_log):
    """MCP mutations run off the GUI thread. Creating a joint probed the
    joint's ViewObject there, which raised "GUI API 'getViewObject' may only be
    used from the main thread", so no joint could be created in a live GUI."""

    assert_ok(mcp.call("create_document", name="LiveAsm"))
    assert_ok(mcp.call("create_assembly", doc_name="LiveAsm", assembly_name="Asm"))
    assert_ok(mcp.call("create_object", doc_name="LiveAsm", obj_type="Part::Box",
                       obj_name="BoxA"))
    assert_ok(mcp.call("create_object", doc_name="LiveAsm", obj_type="Part::Box",
                       obj_name="BoxB", obj_properties={"Placement": {"Base": {"x": 30}}}))
    for box in ("BoxA", "BoxB"):
        assert_ok(mcp.call("move_object", doc_name="LiveAsm", obj_name=box,
                           target_container="Asm"))

    assert_ok(mcp.call("create_assembly_grounded_joint", doc_name="LiveAsm",
                       assembly_name="Asm", component_name="BoxA"))
    assert_ok(mcp.call("create_assembly_joint", doc_name="LiveAsm", assembly_name="Asm",
                       joint_type="Fixed", ref1_component="BoxA", ref1_element="Face2",
                       ref2_component="BoxB", ref2_element="Face1"))
    assert_ok(mcp.call("solve_assembly", doc_name="LiveAsm", assembly_name="Asm"))
    assert_ok(mcp.call("close_document", doc_name="LiveAsm"))
    assert_clean(gui_log)
