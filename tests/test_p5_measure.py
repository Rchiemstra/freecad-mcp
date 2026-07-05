"""
Tests for P5 measurement and transform operations.

Layer-A: Schema / error propagation
Layer-B: Code-fragment and API-call checks
"""
from __future__ import annotations

from unittest.mock import MagicMock

from mcp.types import TextContent

from freecad_mcp.operations.p5_measure import (
    bounding_box_operation,
    center_of_mass_operation,
    measure_angle_operation,
    measure_area_operation,
    measure_distance_operation,
    measure_volume_operation,
    rotate_operation,
    scale_operation,
    translate_operation,
    validate_geometry_operation,
)
from tests.helpers.geometric import assert_code_compiles, assert_code_contains


def _ok_conn():
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {"success": True, "message": "done", "recompute_errors": []}
    return conn


def _fail_conn():
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {"success": False, "error": "oops"}
    return conn


def _code(conn) -> str:
    return conn.execute_code.call_args[0][0]


def _text(response) -> str:
    return " ".join(item.text for item in response if isinstance(item, TextContent))


# ---------------------------------------------------------------------------
# P5-1  measure_distance
# ---------------------------------------------------------------------------

class TestMeasureDistance:
    def test_success(self):
        resp = measure_distance_operation(_ok_conn(), "Doc", "Obj1", "Obj2")
        assert _text(resp)

    def test_failure(self):
        resp = measure_distance_operation(_fail_conn(), "Doc", "Obj1", "Obj2")
        assert "oops" in _text(resp) or "Failed" in _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        measure_distance_operation(conn, "Doc", "Obj1", "Obj2")
        assert_code_compiles(_code(conn))

    def test_distToShape_called(self):
        conn = _ok_conn()
        measure_distance_operation(conn, "Doc", "Obj1", "Obj2")
        assert_code_contains(_code(conn), "distToShape")

    def test_object_names_in_code(self):
        conn = _ok_conn()
        measure_distance_operation(conn, "Doc", "ShapeA", "ShapeB")
        code = _code(conn)
        assert_code_contains(code, "ShapeA", "ShapeB")

    def test_json_output(self):
        conn = _ok_conn()
        measure_distance_operation(conn, "Doc", "A", "B")
        assert_code_contains(_code(conn), "json.dumps")

    def test_unit_mm(self):
        conn = _ok_conn()
        measure_distance_operation(conn, "Doc", "A", "B")
        assert_code_contains(_code(conn), "'mm'")


# ---------------------------------------------------------------------------
# P5-2  measure_angle
# ---------------------------------------------------------------------------

class TestMeasureAngle:
    def test_success(self):
        resp = measure_angle_operation(_ok_conn(), "Doc", "Obj1:Edge1", "Obj2:Edge2")
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        measure_angle_operation(conn, "Doc", "Obj1:Edge1", "Obj2:Edge2")
        assert_code_compiles(_code(conn))

    def test_tangent_at_called(self):
        conn = _ok_conn()
        measure_angle_operation(conn, "Doc", "A:Edge1", "B:Edge2")
        assert_code_contains(_code(conn), "tangentAt")

    def test_acos_in_code(self):
        conn = _ok_conn()
        measure_angle_operation(conn, "Doc", "A", "B")
        assert_code_contains(_code(conn), "math.acos")


# ---------------------------------------------------------------------------
# P5-3  measure_area
# ---------------------------------------------------------------------------

class TestMeasureArea:
    def test_success(self):
        resp = measure_area_operation(_ok_conn(), "Doc", "Obj1")
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        measure_area_operation(conn, "Doc", "Obj1")
        assert_code_compiles(_code(conn))

    def test_area_attribute_read(self):
        conn = _ok_conn()
        measure_area_operation(conn, "Doc", "Box1")
        assert_code_contains(_code(conn), ".Area")

    def test_json_output(self):
        conn = _ok_conn()
        measure_area_operation(conn, "Doc", "Box1")
        assert_code_contains(_code(conn), "area_mm2")


# ---------------------------------------------------------------------------
# P5-4  measure_volume
# ---------------------------------------------------------------------------

class TestMeasureVolume:
    def test_success(self):
        resp = measure_volume_operation(_ok_conn(), "Doc", "Obj1")
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        measure_volume_operation(conn, "Doc", "Obj1")
        assert_code_compiles(_code(conn))

    def test_volume_attribute_read(self):
        conn = _ok_conn()
        measure_volume_operation(conn, "Doc", "Sphere1")
        assert_code_contains(_code(conn), ".Volume")

    def test_json_output(self):
        conn = _ok_conn()
        measure_volume_operation(conn, "Doc", "Sphere1")
        assert_code_contains(_code(conn), "volume_mm3")


# ---------------------------------------------------------------------------
# P5-5  bounding_box
# ---------------------------------------------------------------------------

class TestBoundingBox:
    def test_success(self):
        resp = bounding_box_operation(_ok_conn(), "Doc", "Obj1")
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        bounding_box_operation(conn, "Doc", "Box1")
        assert_code_compiles(_code(conn))

    def test_boundbox_attribute_read(self):
        conn = _ok_conn()
        bounding_box_operation(conn, "Doc", "Box1")
        assert_code_contains(_code(conn), "BoundBox")

    def test_json_has_expected_keys(self):
        conn = _ok_conn()
        bounding_box_operation(conn, "Doc", "Box1")
        code = _code(conn)
        for key in ("xmin", "ymin", "zmin", "xmax", "ymax", "zmax", "dx", "dy", "dz"):
            assert_code_contains(code, f"'{key}'")


# ---------------------------------------------------------------------------
# P5-6  center_of_mass
# ---------------------------------------------------------------------------

class TestCenterOfMass:
    def test_success(self):
        resp = center_of_mass_operation(_ok_conn(), "Doc", "Obj1")
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        center_of_mass_operation(conn, "Doc", "Obj1")
        assert_code_compiles(_code(conn))

    def test_CenterOfMass_attribute(self):
        conn = _ok_conn()
        center_of_mass_operation(conn, "Doc", "Obj1")
        assert_code_contains(_code(conn), "CenterOfMass")

    def test_json_keys(self):
        conn = _ok_conn()
        center_of_mass_operation(conn, "Doc", "Obj1")
        code = _code(conn)
        for key in ("'x'", "'y'", "'z'"):
            assert_code_contains(code, key)


# ---------------------------------------------------------------------------
# P5-7  validate_geometry
# ---------------------------------------------------------------------------

class TestValidateGeometry:
    def test_success(self):
        resp = validate_geometry_operation(_ok_conn(), "Doc", "Obj1")
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        validate_geometry_operation(conn, "Doc", "Obj1")
        assert_code_compiles(_code(conn))

    def test_isValid_check(self):
        conn = _ok_conn()
        validate_geometry_operation(conn, "Doc", "Obj1")
        assert_code_contains(_code(conn), "isValid")

    def test_check_called_with_exception_capture(self):
        conn = _ok_conn()
        validate_geometry_operation(conn, "Doc", "Obj1")
        code = _code(conn)
        assert_code_contains(code, "check(False)", "check_ok", "check_errors", "except Exception as _check_err")
        assert "analyze" not in code


# ---------------------------------------------------------------------------
# P5-8  translate
# ---------------------------------------------------------------------------

class TestTranslate:
    def test_success(self):
        resp = translate_operation(_ok_conn(), True, "Doc", "Obj1", 10, 0, 0)
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        translate_operation(conn, True, "Doc", "Obj1", 10, 5, 3)
        assert_code_compiles(_code(conn))

    def test_placement_modified(self):
        conn = _ok_conn()
        translate_operation(conn, True, "Doc", "Obj1", 10, 0, 0)
        assert_code_contains(_code(conn), "Placement")

    def test_delta_in_code(self):
        conn = _ok_conn()
        translate_operation(conn, True, "Doc", "Obj1", 7.5, -3.0, 2.5)
        code = _code(conn)
        assert_code_contains(code, "7.5", "-3.0", "2.5")

    def test_recompute_called(self):
        conn = _ok_conn()
        translate_operation(conn, True, "Doc", "Obj1", 0, 0, 0)
        assert_code_contains(_code(conn), "_doc.recompute()")


# ---------------------------------------------------------------------------
# P5-9  rotate
# ---------------------------------------------------------------------------

class TestRotate:
    def test_success(self):
        resp = rotate_operation(_ok_conn(), True, "Doc", "Obj1", 0, 0, 1, 90.0)
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        rotate_operation(conn, True, "Doc", "Obj1", 0, 0, 1, 45.0)
        assert_code_compiles(_code(conn))

    def test_rotation_api_called(self):
        conn = _ok_conn()
        rotate_operation(conn, True, "Doc", "Obj1", 0, 0, 1, 90.0)
        assert_code_contains(_code(conn), "FreeCAD.Rotation")

    def test_axis_in_code(self):
        conn = _ok_conn()
        rotate_operation(conn, True, "Doc", "Obj1", 1.0, 0.0, 0.0, 45.0)
        code = _code(conn)
        assert_code_contains(code, "1.0", "0.0")

    def test_angle_in_code(self):
        conn = _ok_conn()
        rotate_operation(conn, True, "Doc", "Obj1", 0, 0, 1, 120.0)
        assert_code_contains(_code(conn), "120.0")

    def test_center_in_code(self):
        conn = _ok_conn()
        rotate_operation(conn, True, "Doc", "Obj1", 0, 0, 1, 45.0, center_x=5.0, center_y=5.0)
        code = _code(conn)
        assert_code_contains(code, "5.0")


# ---------------------------------------------------------------------------
# P5-10  scale
# ---------------------------------------------------------------------------

class TestScale:
    def test_success(self):
        resp = scale_operation(_ok_conn(), True, "Doc", "Obj1", 2.0, 2.0, 2.0)
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        scale_operation(conn, True, "Doc", "Obj1", 2.0, 1.0, 0.5)
        assert_code_compiles(_code(conn))

    def test_matrix_scale_called(self):
        conn = _ok_conn()
        scale_operation(conn, True, "Doc", "Obj1", 2.0, 2.0, 2.0)
        assert_code_contains(_code(conn), "FreeCAD.Matrix")

    def test_scale_factors_in_code(self):
        conn = _ok_conn()
        scale_operation(conn, True, "Doc", "Obj1", 1.5, 2.5, 0.5)
        code = _code(conn)
        assert_code_contains(code, "1.5", "2.5", "0.5")

    def test_transformGeometry_called(self):
        conn = _ok_conn()
        scale_operation(conn, True, "Doc", "Obj1", 2.0, 2.0, 2.0)
        assert_code_contains(_code(conn), "transformGeometry")
