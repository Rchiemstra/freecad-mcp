"""Unit tests for the extended MCP operations layer.

All sketch/pad/utility operations now drive execute_code internally so they
work with the original FreeCAD addon without any addon update or restart.
Tests mock freecad.execute_code (success/failure) and verify that the
generated Python code contains the expected keywords and parameters.
"""
import json
from unittest.mock import MagicMock

from freecad_mcp.operations.core import (
    close_document_operation,
    get_recompute_log_operation,
    get_sketch_diagnostics_operation,
    get_view_operation,
    get_objects_operation,
    sketch_create_operation,
    sketch_add_geometry_operation,
    sketch_add_constraint_operation,
    sketch_add_line_operation,
    sketch_add_circle_operation,
    sketch_add_arc_operation,
    sketch_add_rectangle_operation,
    sketch_constrain_coincident_operation,
    sketch_constrain_horizontal_operation,
    sketch_constrain_vertical_operation,
    sketch_constrain_distance_operation,
    sketch_constrain_radius_operation,
    sketch_constrain_equal_operation,
    sketch_constrain_parallel_operation,
    sketch_constrain_perpendicular_operation,
    sketch_constrain_tangent_operation,
    pad_feature_operation,
    pocket_feature_operation,
    linear_pattern_feature_operation,
    polar_pattern_feature_operation,
    mirror_feature_operation,
    create_spur_gear_operation,
    recompute_document_operation,
    undo_operation,
    redo_operation,
)
from mcp.types import ImageContent, TextContent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _text(response):
    content = response.content if hasattr(response, "content") else response
    return " ".join(item.text for item in content if isinstance(item, TextContent))


def _has_image(response):
    content = response.content if hasattr(response, "content") else response
    return any(isinstance(item, ImageContent) for item in content)


def _ok_conn(output="done", recompute_errors=None):
    """Connection where execute_code always succeeds."""
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {
        "success": True,
        "message": output,
        "recompute_errors": recompute_errors or [],
    }
    return conn


def _fail_conn(error="oops"):
    """Connection where execute_code always fails."""
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {"success": False, "error": error}
    return conn


def _code(conn) -> str:
    """Return the code string passed to execute_code on the last call."""
    return conn.execute_code.call_args[0][0]


def _assert_generated_code_compiles(conn):
    """Generated snippets are sent to FreeCAD as exec() code."""
    compile(_code(conn), "<freecad-mcp-generated>", "exec")


# ---------------------------------------------------------------------------
# get_view_operation
# ---------------------------------------------------------------------------

class TestGetViewOperation:
    def test_text_and_image_when_screenshot_available(self):
        conn = MagicMock()
        conn.get_active_screenshot.return_value = "base64data"
        result = get_view_operation(conn, "Isometric")
        assert _has_image(result)
        assert any(isinstance(i, TextContent) for i in (result.content if hasattr(result, "content") else result))

    def test_text_only_when_no_screenshot(self):
        conn = MagicMock()
        conn.get_active_screenshot.return_value = None
        result = get_view_operation(conn, "Front")
        assert not _has_image(result)
        assert "Cannot get screenshot" in _text(result)

    def test_label_contains_view_and_focus(self):
        conn = MagicMock()
        conn.get_active_screenshot.return_value = "data"
        t = _text(get_view_operation(conn, "Top", focus_object="Box"))
        assert "Top" in t and "Box" in t

    def test_multi_object_focus_passed_through(self):
        conn = MagicMock()
        conn.get_active_screenshot.return_value = "data"
        result = get_view_operation(
            conn,
            "Isometric",
            focus_objects=["StationA", "StationB"],
            yaw_deg=45,
        )
        assert _has_image(result)
        conn.get_active_screenshot.assert_called_once()
        kwargs = conn.get_active_screenshot.call_args.kwargs
        assert kwargs["focus_objects"] == ["StationA", "StationB"]
        assert kwargs["yaw_deg"] == 45
        assert "StationA" in _text(result) and "45" in _text(result)


class TestSaveViewSequenceOperation:
    def test_returns_multiple_images(self):
        from freecad_mcp.operations.core import save_view_sequence_operation

        conn = MagicMock()
        conn.capture_view_sequence.return_value = {
            "ok": True,
            "frame_count": 2,
            "ok_count": 2,
            "frames": [
                {
                    "index": 0,
                    "ok": True,
                    "label": "orbit_00",
                    "view_name": "Isometric",
                    "focus_objects": ["Box"],
                    "yaw_deg": 0,
                    "image_base64": "img0",
                },
                {
                    "index": 1,
                    "ok": True,
                    "label": "orbit_01",
                    "view_name": "Isometric",
                    "focus_objects": ["Box"],
                    "yaw_deg": 180,
                    "image_base64": "img1",
                },
            ],
        }
        result = save_view_sequence_operation(conn, orbit={"focus_objects": ["Box"], "steps": 2})
        images = [
            item for item in (result.content if hasattr(result, "content") else result)
            if isinstance(item, ImageContent)
        ]
        assert len(images) == 2
        assert result.structuredContent["ok_count"] == 2

    def test_failure(self):
        from freecad_mcp.operations.core import save_view_sequence_operation

        conn = MagicMock()
        conn.capture_view_sequence.return_value = {"ok": False, "error": "no view", "frames": []}
        result = save_view_sequence_operation(conn, frames=[{"view_name": "Front"}])
        assert "no view" in _text(result) or "Failed" in _text(result)


# ---------------------------------------------------------------------------
# get_objects_operation
# ---------------------------------------------------------------------------

class TestGetObjectsOperation:
    def _conn(self, objs):
        conn = MagicMock()
        conn.get_active_screenshot.return_value = None
        conn.get_objects.return_value = objs
        return conn

    def test_success_returns_json(self):
        conn = self._conn([{"Name": "Box", "TypeId": "Part::Box"}])
        data = json.loads(_text(get_objects_operation(conn, True, "Doc")))
        assert data[0]["Name"] == "Box"

    def test_rpc_exception_returns_error(self):
        conn = MagicMock()
        conn.get_active_screenshot.return_value = None
        conn.get_objects.side_effect = Exception("shape is invalid")
        assert "Failed to get objects" in _text(get_objects_operation(conn, True, "Doc"))

    def test_partial_results_passed_through(self):
        conn = self._conn([
            {"Name": "Good"},
            {"Name": "Bad", "error": "Serialization failed: invalid shape"},
        ])
        data = json.loads(_text(get_objects_operation(conn, True, "Doc")))
        assert len(data) == 2 and "error" in data[1]


# ---------------------------------------------------------------------------
# sketch_create_operation
# ---------------------------------------------------------------------------

class TestSketchCreateOperation:
    def test_calls_execute_code(self):
        conn = _ok_conn("sketch_name=Sketch")
        sketch_create_operation(conn, True, "Doc", "Sketch")
        conn.execute_code.assert_called_once()

    def test_doc_and_sketch_name_in_code(self):
        conn = _ok_conn()
        sketch_create_operation(conn, True, "MyDoc", "MySk")
        assert "'MyDoc'" in _code(conn) and "'MySk'" in _code(conn)

    def test_body_uses_newObject(self):
        conn = _ok_conn()
        sketch_create_operation(conn, True, "Doc", "Sk", body_name="Body")
        assert "'Body'" in _code(conn) and "newObject" in _code(conn)

    def test_attach_xy_plane_in_code(self):
        conn = _ok_conn()
        sketch_create_operation(conn, True, "Doc", "Sk", attach_to="XY_Plane")
        assert "XY_Plane" in _code(conn) and "MapMode" in _code(conn)

    def test_attach_face_in_code(self):
        conn = _ok_conn()
        sketch_create_operation(conn, True, "Doc", "Sk", attach_to="Box:Face1")
        c = _code(conn)
        assert "'Box'" in c and "'Face1'" in c

    def test_generated_code_compiles_with_body_and_plane_attachment(self):
        conn = _ok_conn()
        sketch_create_operation(conn, True, "Doc", "Sk", body_name="Body", attach_to="XY_Plane")
        _assert_generated_code_compiles(conn)

    def test_generated_code_compiles_with_face_attachment(self):
        conn = _ok_conn()
        sketch_create_operation(conn, True, "Doc", "Sk", attach_to="Box:Face1")
        _assert_generated_code_compiles(conn)

    def test_failure_message(self):
        assert "Failed" in _text(sketch_create_operation(_fail_conn(), True, "Doc", "Sk"))


# ---------------------------------------------------------------------------
# sketch_add_geometry_operation
# ---------------------------------------------------------------------------

class TestSketchAddGeometryOperation:
    def test_success_calls_execute_code(self):
        conn = _ok_conn("indices=[0,1,2,3]")
        sketch_add_geometry_operation(conn, True, "Doc", "Sk", [
            {"type": "rectangle", "x1": 0, "y1": 0, "x2": 10, "y2": 10}
        ])
        conn.execute_code.assert_called_once()

    def test_sketch_name_in_code(self):
        conn = _ok_conn()
        sketch_add_geometry_operation(conn, True, "Doc", "MySk", [])
        assert "'MySk'" in _code(conn)

    def test_line_coords_in_code(self):
        conn = _ok_conn()
        sketch_add_geometry_operation(conn, True, "Doc", "Sk", [
            {"type": "line", "start": {"x": 1.5, "y": 2.5}, "end": {"x": 3.0, "y": 4.0}}
        ])
        c = _code(conn)
        assert "1.5" in c and "2.5" in c and "3.0" in c

    def test_circle_in_code(self):
        conn = _ok_conn()
        sketch_add_geometry_operation(conn, True, "Doc", "Sk", [
            {"type": "circle", "center": {"x": 5, "y": 5}, "radius": 3}
        ])
        assert "Circle" in _code(conn)

    def test_arc_in_code(self):
        conn = _ok_conn()
        sketch_add_geometry_operation(conn, True, "Doc", "Sk", [
            {"type": "arc", "center": {"x": 0, "y": 0}, "radius": 5,
             "start_angle": 0, "end_angle": 90}
        ])
        assert "ArcOfCircle" in _code(conn)

    def test_screenshot_attached(self):
        conn = _ok_conn()
        conn.get_active_screenshot.return_value = "imgdata"
        assert _has_image(sketch_add_geometry_operation(conn, False, "Doc", "Sk", []))

    def test_failure(self):
        assert "Failed" in _text(sketch_add_geometry_operation(_fail_conn(), True, "Doc", "Sk", []))


# ---------------------------------------------------------------------------
# sketch_add_constraint_operation
# ---------------------------------------------------------------------------

class TestSketchAddConstraintOperation:
    def test_success(self):
        conn = _ok_conn()
        result = sketch_add_constraint_operation(conn, True, "Doc", "Sk", [
            {"type": "Horizontal", "geo": 0}
        ])
        conn.execute_code.assert_called_once()
        assert "Constraints added" in _text(result)

    def test_constraint_type_in_code(self):
        conn = _ok_conn()
        sketch_add_constraint_operation(conn, True, "Doc", "Sk", [
            {"type": "Coincident", "geo1": 0, "pos1": 1, "geo2": 1, "pos2": 2}
        ])
        assert "Coincident" in _code(conn)

    def test_failure(self):
        assert "Failed" in _text(sketch_add_constraint_operation(_fail_conn(), True, "Doc", "Sk", []))


# ---------------------------------------------------------------------------
# pad_feature_operation
# ---------------------------------------------------------------------------

class TestPadFeatureOperation:
    def test_success(self):
        # pad/pocket now return a structured JSON workflow result.
        conn = _ok_conn('{"ok": true, "feature": "Pad", "body": "Body", "tip": "Pad", "solid_count": 1}')
        result = pad_feature_operation(conn, True, "Doc", "Sk", "Pad", 15.0)
        assert not result.isError
        assert '"feature": "Pad"' in _text(result)

    def test_params_in_code(self):
        conn = _ok_conn()
        pad_feature_operation(conn, True, "Doc", "Sk", "MyPad", 25.0, body_name="Body")
        c = _code(conn)
        assert "25.0" in c and "'MyPad'" in c and "'Body'" in c

    def test_symmetric_in_code(self):
        conn = _ok_conn()
        pad_feature_operation(conn, True, "Doc", "Sk", "P", 10, symmetric=True)
        c = _code(conn)
        assert "True" in c and "SideType" in c

    def test_does_not_assign_symmetric_property_directly(self):
        conn = _ok_conn()
        pad_feature_operation(conn, True, "Doc", "Sk", "P", 10, symmetric=True)
        assert "_pad.Symmetric =" not in _code(conn)

    def test_does_not_set_deprecated_midplane_for_default_one_side(self):
        conn = _ok_conn()
        pad_feature_operation(conn, True, "Doc", "Sk", "P", 10)
        c = _code(conn)
        assert "_set_extrusion_symmetric(_pad, False)" in c
        assert "setattr(_feature, 'Midplane', True)" in c
        assert "setattr(_feature, 'Midplane', False)" not in c

    def test_generated_code_compiles(self):
        conn = _ok_conn()
        pad_feature_operation(conn, True, "Doc", "Sk", "P", 10, symmetric=True, reversed_dir=True)
        _assert_generated_code_compiles(conn)

    def test_failure(self):
        assert "Failed" in _text(pad_feature_operation(_fail_conn(), True, "Doc", "Sk", "P", 10))


# ---------------------------------------------------------------------------
# pocket_feature_operation
# ---------------------------------------------------------------------------

class TestPocketFeatureOperation:
    def test_success(self):
        # pad/pocket now return a structured JSON workflow result.
        conn = _ok_conn('{"ok": true, "feature": "Pocket", "body": "Body", "tip": "Pocket", "solid_count": 1}')
        result = pocket_feature_operation(conn, True, "Doc", "Sk", "Pocket", 5.0)
        assert not result.isError
        assert '"feature": "Pocket"' in _text(result)

    def test_does_not_assign_symmetric_property_directly(self):
        conn = _ok_conn()
        pocket_feature_operation(conn, True, "Doc", "Sk", "P", 5, symmetric=True)
        c = _code(conn)
        assert "SideType" in c and "_pkt.Symmetric =" not in c

    def test_generated_code_compiles(self):
        conn = _ok_conn()
        pocket_feature_operation(conn, True, "Doc", "Sk", "P", 5, symmetric=True, reversed_dir=True)
        _assert_generated_code_compiles(conn)

    def test_failure(self):
        assert "Failed" in _text(pocket_feature_operation(_fail_conn(), True, "Doc", "Sk", "P", 5))


# ---------------------------------------------------------------------------
# PartDesign pattern operations
# ---------------------------------------------------------------------------

class TestLinearPatternFeatureOperation:
    def test_success(self):
        conn = _ok_conn("pattern_name=Array")
        result = linear_pattern_feature_operation(conn, True, "Doc", "Pocket", "Array", 40.0, 5)
        assert "Linear pattern" in _text(result) and "created" in _text(result)

    def test_params_in_code(self):
        conn = _ok_conn()
        linear_pattern_feature_operation(
            conn, True, "Doc", "Pocket", "Array", 40.0, 5,
            direction="Pad:Edge1", body_name="Body", reversed_dir=True,
        )
        c = _code(conn)
        assert "PartDesign::LinearPattern" in c
        assert "'Pocket'" in c and "'Array'" in c and "float(40.0)" in c and "int(5)" in c
        assert "'Pad:Edge1'" in c and "'Body'" in c and "Reversed" in c

    def test_generated_code_compiles(self):
        conn = _ok_conn()
        linear_pattern_feature_operation(conn, True, "Doc", "Pocket", "Array", 40.0, 5)
        _assert_generated_code_compiles(conn)

    def test_failure(self):
        assert "Failed" in _text(linear_pattern_feature_operation(_fail_conn(), True, "Doc", "Pocket", "Array", 40.0, 5))


class TestPolarPatternFeatureOperation:
    def test_success(self):
        conn = _ok_conn("pattern_name=BoltCircle")
        result = polar_pattern_feature_operation(conn, True, "Doc", "Pocket", "BoltCircle", 6)
        assert "Polar pattern" in _text(result) and "created" in _text(result)

    def test_params_in_code(self):
        conn = _ok_conn()
        polar_pattern_feature_operation(
            conn, True, "Doc", "Pocket", "BoltCircle", 6,
            angle=180.0, axis="AxisObj:Edge2", body_name="Body", reversed_dir=True,
        )
        c = _code(conn)
        assert "PartDesign::PolarPattern" in c
        assert "'Pocket'" in c and "'BoltCircle'" in c and "float(180.0)" in c and "int(6)" in c
        assert "'AxisObj:Edge2'" in c and "'Body'" in c and "Reversed" in c

    def test_generated_code_compiles(self):
        conn = _ok_conn()
        polar_pattern_feature_operation(conn, True, "Doc", "Pocket", "BoltCircle", 6)
        _assert_generated_code_compiles(conn)

    def test_failure(self):
        assert "Failed" in _text(polar_pattern_feature_operation(_fail_conn(), True, "Doc", "Pocket", "BoltCircle", 6))


class TestMirrorFeatureOperation:
    def test_success(self):
        conn = _ok_conn("mirror_name=PocketMirror")
        result = mirror_feature_operation(conn, True, "Doc", "Pocket", "PocketMirror")
        assert "Mirror feature" in _text(result) and "created" in _text(result)

    def test_params_in_code(self):
        conn = _ok_conn()
        mirror_feature_operation(conn, True, "Doc", "Pocket", "PocketMirror", plane="Pad:Face1", body_name="Body")
        c = _code(conn)
        assert "PartDesign::Mirrored" in c
        assert "'Pocket'" in c and "'PocketMirror'" in c and "'Pad:Face1'" in c and "'Body'" in c

    def test_generated_code_compiles(self):
        conn = _ok_conn()
        mirror_feature_operation(conn, True, "Doc", "Pocket", "PocketMirror")
        _assert_generated_code_compiles(conn)

    def test_failure(self):
        assert "Failed" in _text(mirror_feature_operation(_fail_conn(), True, "Doc", "Pocket", "PocketMirror"))


# ---------------------------------------------------------------------------
# create_spur_gear_operation
# ---------------------------------------------------------------------------

class TestCreateSpurGearOperation:
    def test_success(self):
        conn = _ok_conn("pad_name=Gear\nsketch_name=Gear_Sketch\nteeth=24\nmodule=2.0")
        result = create_spur_gear_operation(conn, True, "Doc", "Gear", 24, 2.0, 10.0)
        assert "Spur gear" in _text(result) and "sketch and pad created" in _text(result)

    def test_params_in_code(self):
        conn = _ok_conn()
        create_spur_gear_operation(
            conn,
            True,
            "Doc",
            "Gear24",
            24,
            2.0,
            10.0,
            pressure_angle=20.0,
            bore_diameter=6.0,
        )
        c = _code(conn)
        assert "'Gear24'" in c and "_teeth = int(24)" in c and "_bore_diameter = float(6.0)" in c

    def test_tooth_profile_in_code(self):
        conn = _ok_conn()
        create_spur_gear_operation(
            conn, True, "Doc", "Gear24", 24, 2.0, 10.0,
            tooth_profile="trapezoid",
        )
        c = _code(conn)
        assert "_tooth_profile = 'trapezoid'" in c
        assert "_valid_profiles" in c
        assert "_build_trapezoid_points" in c
        assert "_build_straight_points" in c
        assert "_build_pin_points" in c

    def test_uses_sketch_and_pad_workflow(self):
        conn = _ok_conn()
        create_spur_gear_operation(conn, True, "Doc", "Gear24", 24, 2.0, 10.0)
        c = _code(conn)
        assert "Sketcher::SketchObject" in c
        assert "PartDesign::Pad" in c
        assert "Part::Feature" not in c
        assert "Sketcher.Constraint('Coincident'" in c
        assert "_set_extrusion_symmetric(_pad, False)" in c
        assert "setattr(_feature, 'Midplane', False)" not in c

    def test_generated_code_compiles(self):
        conn = _ok_conn()
        create_spur_gear_operation(conn, True, "Doc", "Gear", 24, 2.0, 10.0)
        _assert_generated_code_compiles(conn)

    def test_generated_code_compiles_for_each_tooth_profile(self):
        for profile in ["involute", "cycloidal", "trapezoid", "straight", "circular_arc", "pin"]:
            conn = _ok_conn()
            create_spur_gear_operation(
                conn, True, "Doc", "Gear", 24, 2.0, 10.0,
                tooth_profile=profile,
            )
            _assert_generated_code_compiles(conn)

    def test_generated_code_compiles_for_profile_aliases(self):
        for profile in ["straight_teeth", "novikov", "lantern"]:
            conn = _ok_conn()
            create_spur_gear_operation(
                conn, True, "Doc", "Gear", 24, 2.0, 10.0,
                tooth_profile=profile,
            )
            _assert_generated_code_compiles(conn)

    def test_failure(self):
        assert "Failed" in _text(create_spur_gear_operation(_fail_conn(), True, "Doc", "Gear", 24, 2.0, 10.0))


# ---------------------------------------------------------------------------
# recompute / undo / redo via execute_code
# ---------------------------------------------------------------------------

class TestDocumentOpsViaCode:
    def test_recompute_success(self):
        conn = _ok_conn("recomputed")
        conn.execute_code.assert_not_called()
        result = recompute_document_operation(conn, "Doc")
        conn.execute_code.assert_called_once()
        assert "recomputed" in _text(result).lower()

    def test_recompute_failure(self):
        assert "Failed" in _text(recompute_document_operation(_fail_conn(), "Doc"))

    def test_undo_success(self):
        conn = _ok_conn("undo done")
        result = undo_operation(conn, "Doc")
        conn.execute_code.assert_called_once()
        assert "undo" in _text(result).lower()

    def test_undo_failure(self):
        assert "Failed" in _text(undo_operation(_fail_conn(), "Doc"))

    def test_redo_success(self):
        conn = _ok_conn("redo done")
        result = redo_operation(conn, "Doc")
        conn.execute_code.assert_called_once()
        assert "redo" in _text(result).lower()

    def test_redo_failure(self):
        assert "Failed" in _text(redo_operation(_fail_conn(), "Doc"))


# ---------------------------------------------------------------------------
# Flat geometry helpers — each drives execute_code
# ---------------------------------------------------------------------------

class TestFlatGeometryHelpers:
    def test_add_line_calls_execute_code(self):
        conn = _ok_conn("geometry_index=0")
        result = sketch_add_line_operation(conn, True, "Doc", "Sk", 0, 0, 10, 0)
        conn.execute_code.assert_called_once()
        assert "Line" in _text(result)

    def test_line_coords_in_code(self):
        conn = _ok_conn()
        sketch_add_line_operation(conn, True, "Doc", "Sk", 1.5, 2.5, 3.0, 4.0)
        c = _code(conn)
        assert "1.5" in c and "2.5" in c and "4.0" in c

    def test_construction_flag_in_code(self):
        conn = _ok_conn()
        sketch_add_line_operation(conn, True, "Doc", "Sk", 0, 0, 1, 0, construction=True)
        assert "True" in _code(conn)

    def test_add_circle_calls_execute_code(self):
        conn = _ok_conn("geometry_index=1")
        result = sketch_add_circle_operation(conn, True, "Doc", "Sk", 5, 5, 3)
        conn.execute_code.assert_called_once()
        assert "Circle" in _text(result)

    def test_circle_params_in_code(self):
        conn = _ok_conn()
        sketch_add_circle_operation(conn, True, "Doc", "Sk", 7, 8, 4)
        c = _code(conn)
        assert "7" in c and "8" in c and "4" in c

    def test_add_arc_calls_execute_code(self):
        conn = _ok_conn("geometry_index=2")
        result = sketch_add_arc_operation(conn, True, "Doc", "Sk", 0, 0, 5, 0, 90)
        conn.execute_code.assert_called_once()
        assert "Arc" in _text(result)

    def test_arc_angles_in_code(self):
        conn = _ok_conn()
        sketch_add_arc_operation(conn, True, "Doc", "Sk", 0, 0, 5, 30, 150)
        c = _code(conn)
        assert "30" in c and "150" in c and "ArcOfCircle" in c

    def test_add_rectangle_calls_execute_code(self):
        conn = _ok_conn("indices=[0,1,2,3]")
        result = sketch_add_rectangle_operation(conn, True, "Doc", "Sk", 0, 0, 10, 5)
        conn.execute_code.assert_called_once()
        assert "Rectangle" in _text(result)

    def test_rectangle_coords_in_code(self):
        conn = _ok_conn()
        sketch_add_rectangle_operation(conn, True, "Doc", "Sk", -5, -3, 5, 3)
        c = _code(conn)
        assert "-5" in c and "-3" in c

    def test_failure_reported(self):
        result = sketch_add_line_operation(_fail_conn("sketch not found"), True, "Doc", "Sk", 0, 0, 1, 0)
        assert "Failed" in _text(result)


# ---------------------------------------------------------------------------
# Flat constraint helpers — each drives execute_code
# ---------------------------------------------------------------------------

class TestFlatConstraintHelpers:
    def test_coincident_in_code(self):
        conn = _ok_conn()
        result = sketch_constrain_coincident_operation(conn, True, "Doc", "Sk", 0, 1, 1, 2)
        assert "Coincident" in _code(conn) and "Coincident" in _text(result)

    def test_horizontal_in_code(self):
        conn = _ok_conn()
        sketch_constrain_horizontal_operation(conn, True, "Doc", "Sk", 0)
        assert "Horizontal" in _code(conn)

    def test_vertical_in_code(self):
        conn = _ok_conn()
        sketch_constrain_vertical_operation(conn, True, "Doc", "Sk", 1)
        assert "Vertical" in _code(conn)

    def test_distance_value_in_code(self):
        conn = _ok_conn()
        sketch_constrain_distance_operation(conn, True, "Doc", "Sk", 0, 20.0)
        c = _code(conn)
        assert "Distance" in c and "20.0" in c

    def test_distance_with_pos_in_code(self):
        conn = _ok_conn()
        sketch_constrain_distance_operation(conn, True, "Doc", "Sk", 0, 5.0, pos=1)
        c = _code(conn)
        assert "5.0" in c and "1" in c

    def test_radius_in_code(self):
        conn = _ok_conn()
        result = sketch_constrain_radius_operation(conn, True, "Doc", "Sk", 2, 7.5)
        assert "Radius" in _code(conn) and "Radius" in _text(result)

    def test_equal_in_code(self):
        conn = _ok_conn()
        sketch_constrain_equal_operation(conn, True, "Doc", "Sk", 0, 2)
        assert "Equal" in _code(conn)

    def test_parallel_in_code(self):
        conn = _ok_conn()
        sketch_constrain_parallel_operation(conn, True, "Doc", "Sk", 0, 2)
        assert "Parallel" in _code(conn)

    def test_perpendicular_in_code(self):
        conn = _ok_conn()
        sketch_constrain_perpendicular_operation(conn, True, "Doc", "Sk", 0, 1)
        assert "Perpendicular" in _code(conn)

    def test_tangent_in_code(self):
        conn = _ok_conn()
        sketch_constrain_tangent_operation(conn, True, "Doc", "Sk", 0, 1)
        assert "Tangent" in _code(conn)

    def test_failure_reported(self):
        result = sketch_constrain_horizontal_operation(_fail_conn("bad type"), True, "Doc", "Sk", 0)
        assert "Failed" in _text(result)


# ---------------------------------------------------------------------------
# Recompute error surfacing in _run_code
# ---------------------------------------------------------------------------

class TestRecomputeErrorsInResponse:
    def test_no_errors_no_warning(self):
        conn = _ok_conn("all good", recompute_errors=[])
        result = sketch_add_line_operation(conn, True, "Doc", "Sk", 0, 0, 10, 0)
        assert "Recompute errors" not in _text(result)

    def test_errors_surfaced_in_message(self):
        errs = [{"name": "Pad", "doc": "Part", "state": ["Invalid"], "label": "Pad"}]
        conn = _ok_conn("ran ok", recompute_errors=errs)
        result = sketch_add_line_operation(conn, True, "Doc", "Sk", 0, 0, 10, 0)
        t = _text(result)
        assert "Recompute errors" in t and "Pad" in t

    def test_multiple_errors_all_listed(self):
        errs = [
            {"name": "Pad", "doc": "Part", "state": ["Invalid"], "label": "Pad"},
            {"name": "Pocket", "doc": "Part", "state": ["Error"], "label": "Pocket"},
        ]
        # pad returns a JSON payload (ends with "}"), so _run_json_code appends the
        # addon-classified recompute_errors after it.
        conn = _ok_conn('{"ok": true, "feature": "Pad"}', recompute_errors=errs)
        result = pad_feature_operation(conn, True, "Doc", "Sk", "Pad", 10.0)
        t = _text(result)
        assert "Pad" in t and "Pocket" in t


# ---------------------------------------------------------------------------
# get_recompute_log_operation
# ---------------------------------------------------------------------------

class TestGetRecomputeLogOperation:
    def test_calls_execute_code(self):
        conn = _ok_conn()
        get_recompute_log_operation(conn, "MyDoc")
        conn.execute_code.assert_called_once()

    def test_doc_name_in_code(self):
        conn = _ok_conn()
        get_recompute_log_operation(conn, "MyDoc")
        assert "'MyDoc'" in _code(conn)

    def test_code_uses_getDocument(self):
        conn = _ok_conn()
        get_recompute_log_operation(conn, "Part")
        assert "getDocument" in _code(conn)

    def test_code_checks_state(self):
        conn = _ok_conn()
        get_recompute_log_operation(conn, "Part")
        assert "State" in _code(conn)

    def test_failure_reported(self):
        result = get_recompute_log_operation(_fail_conn("no doc"), "Part")
        assert "Failed" in _text(result)

    def test_success_message(self):
        result = get_recompute_log_operation(_ok_conn("{}"), "Part")
        assert "Recompute log" in _text(result)


# ---------------------------------------------------------------------------
# get_sketch_diagnostics_operation
# ---------------------------------------------------------------------------

class TestGetSketchDiagnosticsOperation:
    def test_calls_execute_code(self):
        conn = _ok_conn()
        get_sketch_diagnostics_operation(conn, "Doc", "Sketch")
        conn.execute_code.assert_called_once()

    def test_doc_and_sketch_in_code(self):
        conn = _ok_conn()
        get_sketch_diagnostics_operation(conn, "MyDoc", "MySk")
        c = _code(conn)
        assert "'MyDoc'" in c and "'MySk'" in c

    def test_code_queries_geometry_count(self):
        conn = _ok_conn()
        get_sketch_diagnostics_operation(conn, "Doc", "Sk")
        assert "Geometry" in _code(conn)

    def test_code_queries_constraints(self):
        conn = _ok_conn()
        get_sketch_diagnostics_operation(conn, "Doc", "Sk")
        assert "Constraints" in _code(conn)

    def test_code_checks_solver_message(self):
        conn = _ok_conn()
        get_sketch_diagnostics_operation(conn, "Doc", "Sk")
        assert "SolverMessage" in _code(conn)

    def test_code_checks_closed_wire(self):
        conn = _ok_conn()
        get_sketch_diagnostics_operation(conn, "Doc", "Sk")
        assert "isClosed" in _code(conn)

    def test_failure_reported(self):
        result = get_sketch_diagnostics_operation(_fail_conn("no sketch"), "Doc", "Sk")
        assert "Failed" in _text(result)

    def test_success_message(self):
        result = get_sketch_diagnostics_operation(_ok_conn("{}"), "Doc", "Sk")
        assert "diagnostics" in _text(result)


# ---------------------------------------------------------------------------
# close_document_operation
# ---------------------------------------------------------------------------

class TestCloseDocumentOperation:
    def test_calls_execute_code(self):
        conn = _ok_conn()
        close_document_operation(conn, "Part")
        conn.execute_code.assert_called_once()

    def test_doc_name_in_code(self):
        conn = _ok_conn()
        close_document_operation(conn, "MyDoc")
        assert "'MyDoc'" in _code(conn)

    def test_code_calls_closeDocument(self):
        conn = _ok_conn()
        close_document_operation(conn, "Part")
        assert "closeDocument" in _code(conn)

    def test_success_message(self):
        result = close_document_operation(_ok_conn("Document closed"), "Part")
        assert "closed" in _text(result)

    def test_failure_reported(self):
        result = close_document_operation(_fail_conn("not found"), "Part")
        assert "Failed" in _text(result)
