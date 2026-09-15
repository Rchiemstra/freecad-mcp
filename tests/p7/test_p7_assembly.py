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
from freecad_mcp._shared.protocol.create_datum_plane_contract import (
    make_create_datum_plane_failure,
    make_create_datum_plane_success,
)
from freecad_mcp._shared.protocol.create_part_container_contract import (
    make_create_part_container_failure,
    make_create_part_container_success,
)
from freecad_mcp._shared.protocol.create_subshape_binder_contract import (
    make_create_subshape_binder_failure,
    make_create_subshape_binder_success,
)
from freecad_mcp._shared.protocol.get_document_tree_contract import (
    make_get_document_tree_success,
)
from freecad_mcp._shared.protocol.get_sketch_geometry_contract import (
    make_get_sketch_geometry_success,
)
from freecad_mcp._shared.protocol.move_object_contract import (
    make_move_object_failure,
    make_move_object_success,
)
from freecad_mcp._shared.protocol.sketch_add_external_projection_contract import (
    make_sketch_add_external_projection_failure,
    make_sketch_add_external_projection_success,
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


_ASSEMBLY_ACTIONS = (
    Path(__file__).resolve().parents[2]
    / "addon"
    / "FreeCADMCP"
    / "rpc_server"
    / "methods"
    / "cad_methods_ops"
    / "assembly_actions.py"
).read_text(encoding="utf-8")


def _ok_conn():
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
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
    conn.create_part_container.return_value = make_create_part_container_success(
        "CableVisualization", "CableVisualization"
    )
    conn.move_object.return_value = make_move_object_success("Sketch", "Body")
    conn.create_subshape_binder.return_value = make_create_subshape_binder_success(
        "FinalHolderFusionRef"
    )
    conn.create_datum_plane.return_value = make_create_datum_plane_success("CableDatum", "CableBody")
    conn.sketch_add_external_projection.return_value = make_sketch_add_external_projection_success(
        "Sketch"
    )
    return conn


def _fail_conn(error: str = "oops"):
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.create_part_container.return_value = make_create_part_container_failure("FAILED", error)
    conn.move_object.return_value = make_move_object_failure("FAILED", error)
    conn.create_subshape_binder.return_value = make_create_subshape_binder_failure("FAILED", error)
    conn.create_datum_plane.return_value = make_create_datum_plane_failure("FAILED", error)
    conn.sketch_add_external_projection.return_value = make_sketch_add_external_projection_failure(
        "FAILED", error
    )
    return conn


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
        conn.create_part_container.assert_called_once_with("Doc", "CableVisualization", None, "replace")
        conn.execute_code.assert_not_called()

    def test_invalid_if_exists(self):
        resp = create_part_container_operation(_ok_conn(), True, "Doc", "Part", if_exists="bad")
        assert "if_exists" in _text(resp)


class TestMoveObject:
    def test_compiles_and_reparents(self):
        conn = _ok_conn()
        resp = move_object_operation(conn, True, "Doc", "Sketch", "Body")
        assert not resp.isError
        conn.move_object.assert_called_once_with("Doc", "Sketch", "Body", True)
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
        conn.create_subshape_binder.assert_called_once_with(
            "Doc",
            "FinalHolderFusionRef",
            "Final_Holder_Fusion",
            ["Face71"],
            "CableBody",
            None,
            False,
            True,
            "error",
        )
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
        conn.create_datum_plane.assert_called_once_with(
            "Doc",
            "CableDatum",
            "CableBody",
            "midpoint_between_faces",
            None,
            "A:Face1",
            "B:Face2",
            [0, 0, -0.55],
            "FlatFace",
            "error",
        )
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
        conn.sketch_add_external_projection.assert_called_once_with(
            "Doc", "Sketch", "Binder:Face1", "auto", False, True
        )
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
        assert conn.sketch_add_external_projection.call_args.args[1] == "Sketch"

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
