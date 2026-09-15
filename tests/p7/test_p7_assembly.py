"""
Tests for P7 assembly/reference and sketch introspection operations.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from mcp.types import TextContent

from freecad_mcp._shared.protocol.create_assembly_contract import (
    make_create_assembly_success,
)
from freecad_mcp._shared.protocol.create_assembly_grounded_joint_contract import (
    make_create_assembly_grounded_joint_success,
)
from freecad_mcp._shared.protocol.create_assembly_joint_contract import (
    make_create_assembly_joint_success,
)
from freecad_mcp._shared.protocol.get_document_tree_contract import (
    make_get_document_tree_success,
)
from freecad_mcp._shared.protocol.get_sketch_geometry_contract import (
    make_get_sketch_geometry_success,
)
from freecad_mcp.operations.p7_assembly import (
    create_assembly_grounded_joint_operation,
    create_assembly_joint_operation,
    create_assembly_operation,
    create_datum_plane_operation,
    create_part_container_operation,
    create_subshape_binder_operation,
    get_document_tree_operation,
    get_sketch_geometry_operation,
    move_object_operation,
    sketch_add_external_projection_operation,
)
from tests.helpers.geometric import assert_code_compiles, assert_code_contains


def _typed_ok(**fields):
    payload = {
        "contract_version": 1,
        "success": True,
        "ok": True,
        "outcome": "committed",
        "committed": True,
        "retry_safe": False,
        "part_name": "Part",
        "label": "Label",
        "object_name": "Obj",
        "target_container": "Body",
        "binder_name": "Binder",
        "plane_name": "Plane",
        "body_name": "Body",
        "sketch_name": "Sketch",
        "wire_name": "Wire",
        "solid_name": "Solid",
    }
    payload.update(fields)
    return payload


_ASSEMBLY_ACTIONS = (
    Path(__file__).resolve().parents[2]
    / "addon"
    / "FreeCADMCP"
    / "rpc_server"
    / "methods"
    / "cad_methods_ops"
    / "assembly_actions.py"
).read_text(encoding="utf-8")


def _ok_conn(output: str = '{"ok": true}'):
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {
        "success": True,
        "message": "Python code execution scheduled. \nOutput: " + output,
        "recompute_errors": [],
    }
    conn._invoke_mutation_v2.return_value = _typed_ok()
    conn.create_assembly.return_value = make_create_assembly_success(
        "MainAssembly", "MainAssembly", "Assembly::AssemblyObject", "JointGroup"
    )
    conn.create_assembly_grounded_joint.return_value = make_create_assembly_grounded_joint_success(
        "Ground", "Ground", "Grounded", "Assembly", "BaseLink"
    )
    conn.create_assembly_joint.return_value = make_create_assembly_joint_success(
        "Screw 1", "Screw 1", "Cylindrical", "Assembly"
    )
    conn.get_document_tree.return_value = make_get_document_tree_success(
        "Doc", "Cable", 3, [{"name": "Cable", "children": []}]
    )
    conn.get_sketch_geometry.return_value = make_get_sketch_geometry_success(
        "CableRouteSketch", 2, [], [], []
    )
    return conn


def _fail_conn():
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {"success": False, "error": "oops"}
    conn._invoke_mutation_v2.return_value = {
        "contract_version": 1,
        "success": False,
        "ok": False,
        "outcome": "rejected",
        "committed": False,
        "retry_safe": True,
        "error_code": "FAILED",
        "error": "oops",
    }
    return conn


def _code(conn) -> str:
    return conn.execute_code.call_args[0][0]


def _text(response) -> str:
    content = response.content if hasattr(response, "content") else response
    return " ".join(item.text for item in content if isinstance(item, TextContent))


class TestDocumentTree:
    def test_routes_typed_rpc(self):
        conn = _ok_conn()
        get_document_tree_operation(conn, "Doc", root_filter="Cable", max_depth=3)
        conn.get_document_tree.assert_called_once_with("Doc", "Cable", 3, None, None, None)
        conn.execute_code.assert_not_called()

    def test_json_output_is_returned_directly(self):
        resp = get_document_tree_operation(_ok_conn(), "Doc", root_filter="Cable", max_depth=3)
        assert '"doc_name": "Doc"' in _text(resp)
        assert '"outcome": "observed"' in _text(resp)


class TestAssemblyApiTools:
    def test_create_assembly_compiles_and_uses_public_api(self):
        conn = _ok_conn()
        create_assembly_operation(conn, True, "Doc", "MainAssembly", if_exists="replace")
        conn.create_assembly.assert_called_once()
        conn.execute_code.assert_not_called()
        assert_code_compiles(_ASSEMBLY_ACTIONS)
        assert_code_contains(
            _ASSEMBLY_ACTIONS, "createAssembly", "getJointGroup", "recompute=False"
        )
        assert conn.create_assembly.call_args.args[1] == "MainAssembly"

    def test_create_assembly_invalid_if_exists(self):
        resp = create_assembly_operation(_ok_conn(), True, "Doc", "Assembly", if_exists="bad")
        assert "if_exists" in _text(resp)

    def test_create_grounded_joint_compiles_and_uses_public_api(self):
        conn = _ok_conn()
        create_assembly_grounded_joint_operation(conn, True, "Doc", "Assembly", "BaseLink", label="Ground")
        conn.create_assembly_grounded_joint.assert_called_once()
        assert_code_compiles(_ASSEMBLY_ACTIONS)
        assert_code_contains(_ASSEMBLY_ACTIONS, "createGroundedJoint", "ObjectToGround")
        assert conn.create_assembly_grounded_joint.call_args.args[2] == "BaseLink"

    def test_create_joint_compiles_and_uses_public_api(self):
        conn = _ok_conn()
        create_assembly_joint_operation(
            conn,
            True,
            "Doc",
            "Assembly",
            "Cylindrical",
            "ScrewLink",
            "PlateLink",
            ref1_element="Edge3",
            ref2_element="Pocket001.Edge1",
            label="Screw 1",
            solve=False,
        )
        conn.create_assembly_joint.assert_called_once()
        conn.execute_code.assert_not_called()
        assert_code_compiles(_ASSEMBLY_ACTIONS)
        assert_code_contains(
            _ASSEMBLY_ACTIONS,
            "makeJointReference",
            "createJoint",
            "solve=solve",
            "presolve=presolve",
            "recompute=False",
        )
        assert conn.create_assembly_joint.call_args.args[6] == "Pocket001.Edge1"


class TestPartContainer:
    def test_compiles_and_creates_app_part(self):
        conn = _ok_conn()
        resp = create_part_container_operation(conn, True, "Doc", "CableVisualization", if_exists="replace")
        assert not resp.isError
        conn._invoke_mutation_v2.assert_called()
        assert conn._invoke_mutation_v2.call_args[0][0] == "create_part_container"
        assert conn._invoke_mutation_v2.call_args[0][1]["part_name"] == "CableVisualization"
        assert conn._invoke_mutation_v2.call_args[0][1]["if_exists"] == "replace"
        conn.execute_code.assert_not_called()

    def test_invalid_if_exists(self):
        resp = create_part_container_operation(_ok_conn(), True, "Doc", "Part", if_exists="bad")
        assert "if_exists" in _text(resp)


class TestMoveObject:
    def test_compiles_and_reparents(self):
        conn = _ok_conn()
        resp = move_object_operation(conn, True, "Doc", "Sketch", "Body")
        assert not resp.isError
        conn._invoke_mutation_v2.assert_called()
        assert conn._invoke_mutation_v2.call_args[0][0] == "move_object"
        assert conn._invoke_mutation_v2.call_args[0][1]["obj_name"] == "Sketch"
        conn.execute_code.assert_not_called()

    def test_failure_propagates(self):
        resp = move_object_operation(_fail_conn(), True, "Doc", "Sketch", "Body")
        assert "oops" in _text(resp)


class TestSubShapeBinder:
    def test_compiles_and_sets_support_placement_and_validation(self):
        conn = _ok_conn()
        resp = create_subshape_binder_operation(
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
        assert not resp.isError
        conn._invoke_mutation_v2.assert_called()
        assert conn._invoke_mutation_v2.call_args[0][0] == "create_subshape_binder"
        assert conn._invoke_mutation_v2.call_args[0][1]["binder_name"] == "FinalHolderFusionRef"
        conn.execute_code.assert_not_called()


class TestDatumPlane:
    def test_compiles_midpoint_between_faces(self):
        conn = _ok_conn()
        resp = create_datum_plane_operation(
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
        assert not resp.isError
        conn._invoke_mutation_v2.assert_called()
        assert conn._invoke_mutation_v2.call_args[0][0] == "create_datum_plane"
        assert conn._invoke_mutation_v2.call_args[0][1]["mode"] == "midpoint_between_faces"
        conn.execute_code.assert_not_called()


class TestSketchGeometry:
    def test_routes_typed_rpc(self):
        conn = _ok_conn()
        get_sketch_geometry_operation(conn, "Doc", "CableRouteSketch")
        conn.get_sketch_geometry.assert_called_once_with("Doc", "CableRouteSketch", True, True, True)
        conn.execute_code.assert_not_called()

    def test_json_output(self):
        resp = get_sketch_geometry_operation(_ok_conn(), "Doc", "CableRouteSketch")
        assert '"sketch_name": "CableRouteSketch"' in _text(resp)
        assert '"outcome": "observed"' in _text(resp)


class TestExternalProjection:
    def test_default_requires_gui_loop_opt_in(self):
        conn = _ok_conn()
        resp = sketch_add_external_projection_operation(
            conn, True, "Doc", "Sketch", "Binder:Face1"
        )
        conn.execute_code.assert_not_called()
        envelope = resp.structuredContent
        assert envelope["error_code"] == "gui_geometry_loop_opt_in_required"
        assert "allow_gui_geometry_loop=true" in envelope["error"]

    def test_compiles_and_preflights(self):
        conn = _ok_conn()
        resp = sketch_add_external_projection_operation(
            conn,
            True,
            "Doc",
            "Sketch",
            "Binder:Face1",
            allow_gui_geometry_loop=True,
        )
        assert not resp.isError
        conn._invoke_mutation_v2.assert_called()
        assert conn._invoke_mutation_v2.call_args[0][0] == "sketch_add_external_projection"
        conn.execute_code.assert_not_called()

    def test_explicit_gui_loop_override_forces_gui_execution(self):
        conn = _ok_conn()
        resp = sketch_add_external_projection_operation(
            conn,
            True,
            "Doc",
            "Sketch",
            "Binder:Face1",
            allow_gui_geometry_loop=True,
        )
        assert not resp.isError
        assert conn._invoke_mutation_v2.call_args[0][1]["sketch_name"] == "Sketch"

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
