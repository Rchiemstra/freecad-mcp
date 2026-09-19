"""
Tests for P5 measurement and transform operations.

Layer-A: Schema / error propagation
Layer-B: Code-fragment and API-call checks
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from mcp.types import TextContent

from freecad_mcp._shared.protocol.bounding_box_contract import (
    make_bounding_box_failure,
    make_bounding_box_success,
)
from freecad_mcp._shared.protocol.center_of_mass_contract import (
    make_center_of_mass_failure,
    make_center_of_mass_success,
)
from freecad_mcp._shared.protocol.common_volume_along_path_contract import (
    make_common_volume_along_path_failure,
    make_common_volume_along_path_success,
)
from freecad_mcp._shared.protocol.rotate_contract import (
    make_rotate_failure,
    make_rotate_success,
)
from freecad_mcp._shared.protocol.scale_contract import (
    make_scale_failure,
    make_scale_success,
)
from freecad_mcp._shared.protocol.get_global_shape_contract import (
    make_get_global_shape_failure,
    make_get_global_shape_success,
)
from freecad_mcp._shared.protocol.measure_angle_contract import (
    make_measure_angle_failure,
    make_measure_angle_success,
)
from freecad_mcp._shared.protocol.measure_area_contract import (
    make_measure_area_failure,
    make_measure_area_success,
)
from freecad_mcp._shared.protocol.measure_distance_contract import (
    make_measure_distance_failure,
    make_measure_distance_success,
)
from freecad_mcp._shared.protocol.measure_volume_contract import (
    make_measure_volume_failure,
    make_measure_volume_success,
)
from freecad_mcp._shared.protocol.translate_contract import (
    make_translate_failure,
    make_translate_success,
)
from freecad_mcp._shared.protocol.validate_geometry_contract import (
    make_validate_geometry_failure,
    make_validate_geometry_success,
)
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


_MEASURE_IO = (
    Path(__file__).resolve().parents[1]
    / "addon"
    / "FreeCADMCP"
    / "rpc_server"
    / "methods"
    / "cad_methods_ops"
    / "measure_io_actions.py"
).read_text(encoding="utf-8")

_MEASURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "addon"
    / "FreeCADMCP"
    / "rpc_server"
    / "methods"
    / "cad_methods_ops"
    / "measure_path_actions.py"
).read_text(encoding="utf-8")


def _ok_conn():
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {"success": True, "message": "done", "recompute_errors": []}
    conn.bounding_box.return_value = make_bounding_box_success(
        "Obj1", 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.732051, "world", False
    )
    conn.center_of_mass.return_value = make_center_of_mass_success(
        "Obj1", 0.0, 0.0, 0.0, "mm", "CenterOfMass", "world"
    )
    conn.common_volume_along_path.return_value = make_common_volume_along_path_success(
        "Mover", 2, 1e-6, 0.0, False, []
    )
    conn.translate.return_value = make_translate_success("Obj1", "Obj1")
    conn.rotate.return_value = make_rotate_success("Obj1", "Obj1")
    conn.scale.return_value = make_scale_success("Obj1", "Obj1")
    conn.measure_distance.return_value = make_measure_distance_success(10.0, "mm")
    conn.measure_angle.return_value = make_measure_angle_success(45.0, "deg")
    conn.measure_area.return_value = make_measure_area_success("Obj1", 100.0, 1.0, "mm2", "world")
    conn.measure_volume.return_value = make_measure_volume_success("Obj1", 1000.0, "mm3", "world", False)
    conn.get_global_shape.return_value = make_get_global_shape_success(
        "Obj1", "world", 1000.0, 600.0, {"x": 0, "y": 0, "z": 0}, {}, 1, 6, 12
    )
    conn.validate_geometry.return_value = make_validate_geometry_success(
        "Obj1", False, True, True, 1000.0, 600.0, 6, 12, 8, "Solid", True, []
    )
    return conn


def _fail_conn():
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {"success": False, "error": "oops"}
    conn.bounding_box.return_value = make_bounding_box_failure("BOUNDING_BOX_FAILED", "oops")
    conn.center_of_mass.return_value = make_center_of_mass_failure("CENTER_OF_MASS_FAILED", "oops")
    conn.common_volume_along_path.return_value = make_common_volume_along_path_failure(
        "COMMON_VOLUME_ALONG_PATH_FAILED", "oops"
    )
    conn.translate.return_value = make_translate_failure("TRANSLATE_FAILED", "oops")
    conn.rotate.return_value = make_rotate_failure("ROTATE_FAILED", "oops")
    conn.scale.return_value = make_scale_failure("SCALE_FAILED", "oops")
    conn.measure_distance.return_value = make_measure_distance_failure("MEASURE_DISTANCE_FAILED", "oops")
    conn.measure_angle.return_value = make_measure_angle_failure("MEASURE_ANGLE_FAILED", "oops")
    conn.measure_area.return_value = make_measure_area_failure("MEASURE_AREA_FAILED", "oops")
    conn.measure_volume.return_value = make_measure_volume_failure("MEASURE_VOLUME_FAILED", "oops")
    conn.get_global_shape.return_value = make_get_global_shape_failure("GET_GLOBAL_SHAPE_FAILED", "oops")
    conn.validate_geometry.return_value = make_validate_geometry_failure("VALIDATE_GEOMETRY_FAILED", "oops")
    return conn


def _text(response) -> str:
    content = response.content if hasattr(response, "content") else response
    return " ".join(item.text for item in content if isinstance(item, TextContent))


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

    def test_routes_typed_rpc(self):
        conn = _ok_conn()
        measure_distance_operation(conn, "Doc", "ShapeA", "ShapeB")
        conn.measure_distance.assert_called_once_with("Doc", "ShapeA", "ShapeB")
        conn.execute_code.assert_not_called()

    def test_json_output(self):
        resp = measure_distance_operation(_ok_conn(), "Doc", "A", "B")
        assert '"distance"' in _text(resp)
        assert '"unit"' in _text(resp)


# ---------------------------------------------------------------------------
# P5-2  measure_angle
# ---------------------------------------------------------------------------

class TestMeasureAngle:
    def test_success(self):
        resp = measure_angle_operation(_ok_conn(), "Doc", "Obj1:Edge1", "Obj2:Edge2")
        assert _text(resp)

    def test_routes_typed_rpc(self):
        conn = _ok_conn()
        measure_angle_operation(conn, "Doc", "A:Edge1", "B:Edge2")
        conn.measure_angle.assert_called_once_with("Doc", "A:Edge1", "B:Edge2")
        conn.execute_code.assert_not_called()

    def test_json_output(self):
        resp = measure_angle_operation(_ok_conn(), "Doc", "A", "B")
        assert '"angle_deg"' in _text(resp)


# ---------------------------------------------------------------------------
# P5-3  measure_area
# ---------------------------------------------------------------------------

class TestMeasureArea:
    def test_success(self):
        resp = measure_area_operation(_ok_conn(), "Doc", "Obj1")
        assert _text(resp)

    def test_routes_typed_rpc(self):
        conn = _ok_conn()
        measure_area_operation(conn, "Doc", "Box1")
        conn.measure_area.assert_called_once_with("Doc", "Box1")
        conn.execute_code.assert_not_called()

    def test_json_output(self):
        resp = measure_area_operation(_ok_conn(), "Doc", "Box1")
        assert '"area_mm2"' in _text(resp)


# ---------------------------------------------------------------------------
# P5-4  measure_volume
# ---------------------------------------------------------------------------

class TestMeasureVolume:
    def test_success(self):
        resp = measure_volume_operation(_ok_conn(), "Doc", "Obj1")
        assert _text(resp)

    def test_routes_typed_rpc(self):
        conn = _ok_conn()
        measure_volume_operation(conn, "Doc", "Sphere1")
        conn.measure_volume.assert_called_once_with("Doc", "Sphere1")
        conn.execute_code.assert_not_called()

    def test_json_output(self):
        resp = measure_volume_operation(_ok_conn(), "Doc", "Sphere1")
        assert '"volume_mm3"' in _text(resp)


# ---------------------------------------------------------------------------
# P5-5  bounding_box
# ---------------------------------------------------------------------------

class TestBoundingBox:
    def test_success(self):
        resp = bounding_box_operation(_ok_conn(), "Doc", "Obj1")
        assert _text(resp)

    def test_compiles(self):
        assert_code_compiles(_MEASURE_IO)

    def test_boundbox_attribute_read(self):
        assert_code_contains(_MEASURE_IO, "resolve_global_shape", "BoundBox")

    def test_json_has_expected_keys(self):
        for key in ("xmin", "ymin", "zmin", "xmax", "ymax", "zmax", "dx", "dy", "dz"):
            assert_code_contains(_MEASURE_IO, f'"{key}"')

    def test_typed_rpc_called(self):
        conn = _ok_conn()
        bounding_box_operation(conn, "Doc", "Box1")
        conn.bounding_box.assert_called_once_with("Doc", "Box1")
        conn.execute_code.assert_not_called()


# ---------------------------------------------------------------------------
# P5-5b  get_global_shape
# ---------------------------------------------------------------------------

class TestGetGlobalShape:
    def test_success(self):
        from freecad_mcp.operations.p5_measure import get_global_shape_operation
        resp = get_global_shape_operation(_ok_conn(), "Doc", "Obj1")
        assert _text(resp)

    def test_routes_typed_rpc(self):
        from freecad_mcp.operations.p5_measure import get_global_shape_operation
        conn = _ok_conn()
        get_global_shape_operation(conn, "Doc", "Link1")
        conn.get_global_shape.assert_called_once_with("Doc", "Link1")
        conn.execute_code.assert_not_called()

    def test_json_output(self):
        from freecad_mcp.operations.p5_measure import get_global_shape_operation
        resp = get_global_shape_operation(_ok_conn(), "Doc", "Link1")
        assert '"volume_mm3"' in _text(resp)
        assert '"bbox"' in _text(resp) or '"area_mm2"' in _text(resp)


# ---------------------------------------------------------------------------
# P5-5c  common_volume_along_path
# ---------------------------------------------------------------------------

class TestCommonVolumeAlongPath:
    def test_success_with_samples(self):
        from freecad_mcp.operations.p5_measure import common_volume_along_path_operation
        resp = common_volume_along_path_operation(
            _ok_conn(),
            "Doc",
            "Mover",
            ["Wall"],
            samples=[{"x": 0, "y": 0, "z": 0}, {"x": 10, "y": 0, "z": 0}],
        )
        assert _text(resp)

    def test_requires_path_or_samples(self):
        from freecad_mcp.operations.p5_measure import common_volume_along_path_operation
        resp = common_volume_along_path_operation(_ok_conn(), "Doc", "Mover", ["Wall"])
        assert "samples" in _text(resp) or "path_object" in _text(resp)

    def test_compiles_path_object(self):
        from freecad_mcp.operations.p5_measure import common_volume_along_path_operation
        conn = _ok_conn()
        common_volume_along_path_operation(
            conn, "Doc", "Mover", ["Wall", "Block"], path_object="Rail", sample_count=5
        )
        assert_code_compiles(_MEASURE_PATH)
        assert_code_contains(_MEASURE_PATH, "resolve_global_shape", "discretize", "common_volume_mm3")
        conn.common_volume_along_path.assert_called_once()

    def test_calls_typed_rpc_not_worker(self):
        from freecad_mcp.operations.p5_measure import common_volume_along_path_operation
        conn = _ok_conn()
        common_volume_along_path_operation(
            conn, "Doc", "Mover", ["Wall"], samples=[{"x": 1, "y": 2, "z": 3}]
        )
        conn.common_volume_along_path.assert_called_once()
        conn.execute_code.assert_not_called()


# ---------------------------------------------------------------------------
# P5-6  center_of_mass
# ---------------------------------------------------------------------------

class TestCenterOfMass:
    def test_success(self):
        resp = center_of_mass_operation(_ok_conn(), "Doc", "Obj1")
        assert _text(resp)

    def test_compiles(self):
        assert_code_compiles(_MEASURE_IO)

    def test_CenterOfMass_attribute(self):
        assert_code_contains(_MEASURE_IO, "CenterOfMass")

    def test_json_keys(self):
        for key in ('"x"', '"y"', '"z"'):
            assert_code_contains(_MEASURE_IO, key)

    def test_typed_rpc_called(self):
        conn = _ok_conn()
        center_of_mass_operation(conn, "Doc", "Obj1")
        conn.center_of_mass.assert_called_once_with("Doc", "Obj1")
        conn.execute_code.assert_not_called()


# ---------------------------------------------------------------------------
# P5-7  validate_geometry
# ---------------------------------------------------------------------------

class TestValidateGeometry:
    def test_success(self):
        resp = validate_geometry_operation(_ok_conn(), "Doc", "Obj1")
        assert _text(resp)

    def test_routes_typed_rpc(self):
        conn = _ok_conn()
        validate_geometry_operation(conn, "Doc", "Obj1")
        conn.validate_geometry.assert_called_once_with("Doc", "Obj1")
        conn.execute_code.assert_not_called()

    def test_json_output(self):
        resp = validate_geometry_operation(_ok_conn(), "Doc", "Obj1")
        assert '"is_valid"' in _text(resp)
        assert '"check_ok"' in _text(resp)


# ---------------------------------------------------------------------------
# P5-8  translate
# ---------------------------------------------------------------------------

class TestTranslate:
    def test_success(self):
        resp = translate_operation(_ok_conn(), True, "Doc", "Obj1", 10, 0, 0)
        assert _text(resp)

    def test_compiles(self):
        assert_code_compiles(_MEASURE_IO)

    def test_placement_modified(self):
        assert_code_contains(_MEASURE_IO, "Placement")

    def test_delta_in_rpc(self):
        conn = _ok_conn()
        translate_operation(conn, True, "Doc", "Obj1", 7.5, -3.0, 2.5)
        conn.translate.assert_called_once_with("Doc", "Obj1", 7.5, -3.0, 2.5)

    def test_apply_does_not_recompute(self):
        assert ".recompute(" not in _MEASURE_IO

    def test_recompute_is_deferred_to_native_postcondition(self):
        assert "Apply never recomputes" in _MEASURE_IO
        assert ".recompute(" not in _MEASURE_IO


class TestRotate:
    def test_success(self):
        resp = rotate_operation(_ok_conn(), True, "Doc", "Obj1", 0, 0, 1, 90.0)
        assert _text(resp)

    def test_compiles(self):
        assert_code_compiles(_MEASURE_IO)

    def test_rotation_api_called(self):
        assert_code_contains(_MEASURE_IO, "Rotation")

    def test_axis_in_rpc(self):
        conn = _ok_conn()
        rotate_operation(conn, True, "Doc", "Obj1", 1.0, 0.0, 0.0, 45.0)
        assert conn.rotate.call_args.args[2:5] == (1.0, 0.0, 0.0)

    def test_angle_in_rpc(self):
        conn = _ok_conn()
        rotate_operation(conn, True, "Doc", "Obj1", 0, 0, 1, 120.0)
        assert conn.rotate.call_args.args[5] == 120.0

    def test_center_in_rpc(self):
        conn = _ok_conn()
        rotate_operation(conn, True, "Doc", "Obj1", 0, 0, 1, 45.0, center_x=5.0, center_y=5.0)
        assert conn.rotate.call_args.args[6:8] == (5.0, 5.0)


class TestScale:
    def test_success(self):
        resp = scale_operation(_ok_conn(), True, "Doc", "Obj1", 2.0, 2.0, 2.0)
        assert _text(resp)

    def test_compiles(self):
        assert_code_compiles(_MEASURE_IO)

    def test_matrix_scale_called(self):
        assert_code_contains(_MEASURE_IO, "Matrix")

    def test_scale_factors_in_rpc(self):
        conn = _ok_conn()
        scale_operation(conn, True, "Doc", "Obj1", 1.5, 2.5, 0.5)
        conn.scale.assert_called_once_with("Doc", "Obj1", 1.5, 2.5, 0.5)

    def test_transformGeometry_called(self):
        assert_code_contains(_MEASURE_IO, "transformGeometry")
