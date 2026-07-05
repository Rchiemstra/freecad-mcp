"""
Tests for P7 assembly/reference and sketch introspection operations.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from mcp.types import TextContent

from freecad_mcp.operations.p7_assembly import (
    create_datum_plane_operation,
    create_part_container_operation,
    create_subshape_binder_operation,
    get_document_tree_operation,
    get_sketch_geometry_operation,
    move_object_operation,
    sketch_add_external_projection_operation,
)
from tests.helpers.geometric import assert_code_compiles, assert_code_contains


def _ok_conn(output: str = '{"ok": true}'):
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {
        "success": True,
        "message": "Python code execution scheduled. \nOutput: " + output,
        "recompute_errors": [],
    }
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


class TestDocumentTree:
    def test_compiles_and_uses_group_tree(self):
        conn = _ok_conn()
        get_document_tree_operation(conn, "Doc", root_filter="Cable", max_depth=3)
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(code, "root_filter", "Group", "children", "max_depth")

    def test_json_output_is_returned_directly(self):
        resp = get_document_tree_operation(_ok_conn('{"doc_name": "Doc"}'), "Doc")
        assert _text(resp).startswith('{"doc_name": "Doc"}')


class TestPartContainer:
    def test_compiles_and_creates_app_part(self):
        conn = _ok_conn()
        create_part_container_operation(conn, True, "Doc", "CableVisualization", if_exists="replace")
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(code, "App::Part", "if_exists", "replace", "_add_to_container")

    def test_invalid_if_exists(self):
        resp = create_part_container_operation(_ok_conn(), True, "Doc", "Part", if_exists="bad")
        assert "if_exists" in _text(resp)


class TestMoveObject:
    def test_compiles_and_reparents(self):
        conn = _ok_conn()
        move_object_operation(conn, True, "Doc", "Sketch", "Body")
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(code, "_remove_from_container", "_add_to_container", "old_parents")

    def test_failure_propagates(self):
        resp = move_object_operation(_fail_conn(), True, "Doc", "Sketch", "Body")
        assert "oops" in _text(resp)


class TestSubShapeBinder:
    def test_compiles_and_sets_support_placement_and_validation(self):
        conn = _ok_conn()
        create_subshape_binder_operation(
            conn,
            True,
            "Doc",
            "FinalHolderFusionRef",
            "Final_Holder_Fusion",
            sub_elements=["Face71"],
            target_body="CableBody",
            relative=False,
            sync_placement=True,
        )
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(
            code,
            "PartDesign::SubShapeBinder",
            "Support",
            "Relative",
            "sync_placement",
            "bbox_delta_mm",
            "0.01",
        )


class TestDatumPlane:
    def test_compiles_midpoint_between_faces(self):
        conn = _ok_conn()
        create_datum_plane_operation(
            conn,
            True,
            "Doc",
            "CableDatum",
            "CableBody",
            "midpoint_between_faces",
            face_a="A:Face1",
            face_b="B:Face2",
            offset_along_normal=[0, 0, -0.55],
        )
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(code, "PartDesign::Plane", "AttachmentSupport", "AttachmentOffset", "midpoint_between_faces")


class TestSketchGeometry:
    def test_compiles_and_reports_external_geometry(self):
        conn = _ok_conn()
        get_sketch_geometry_operation(conn, "Doc", "CableRouteSketch")
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(code, "GeometryFacade", "getGlobalPlacement", "ExternalGeometry", "negative_index")


class TestExternalProjection:
    def test_compiles_and_preflights(self):
        conn = _ok_conn()
        sketch_add_external_projection_operation(conn, True, "Doc", "Sketch", "Binder:Face1")
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(
            code,
            "addExternal",
            "binder and sketch must share parent container",
            "Sketcher::SketchObject",
            "datum normal not parallel to face",
            "candidate_edges",
        )

    def test_invalid_projection_mode(self):
        resp = sketch_add_external_projection_operation(
            _ok_conn(),
            True,
            "Doc",
            "Sketch",
            "Binder:Face1",
            projection_mode="bad",
        )
        assert "projection_mode" in _text(resp)
