"""Unit tests for the diagnostics operations (I1 preview_attachment, and the
later I4/I10/M5/M6 helpers added in the same module)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from mcp.types import TextContent

from freecad_mcp.operations.diagnostics import (
    capture_state_operation,
    edge_axis_operation,
    face_normal_operation,
    find_edges_operation,
    find_faces_operation,
    geometric_diff_operation,
    placement_audit_operation,
    preview_attachment_operation,
    relink_references_operation,
)
from freecad_mcp.operations.p3_features import loft_feature_operation
from freecad_mcp.operations.core import (
    delete_object_operation,
    get_view_operation,
    pad_feature_operation,
    pocket_feature_operation,
)
from freecad_mcp.operations.snapshot import (
    restore_operation,
    snapshot_operation,
)
from freecad_mcp._shared.protocol.capture_state_contract import (
    make_capture_state_failure,
    make_capture_state_success,
)
from freecad_mcp._shared.protocol.create_datum_plane_contract import (
    make_create_datum_plane_failure,
    make_create_datum_plane_success,
)
from freecad_mcp._shared.protocol.delete_object_contract import (
    ObjectName,
    make_delete_object_failure,
    make_delete_object_success,
)
from freecad_mcp._shared.protocol.preview_attachment_contract import (
    make_preview_attachment_failure,
    make_preview_attachment_success,
)
from freecad_mcp._shared.protocol.relink_references_contract import (
    make_relink_references_failure,
    make_relink_references_success,
)
from freecad_mcp._shared.protocol.restore_contract import (
    make_restore_failure,
    make_restore_success,
)
from freecad_mcp._shared.protocol.snapshot_contract import (
    make_snapshot_failure,
    make_snapshot_success,
)
from freecad_mcp._shared.protocol.create_assembly_joint_contract import (
    make_create_assembly_joint_success,
)
from freecad_mcp._shared.protocol.solve_assembly_contract import (
    make_solve_assembly_failure,
    make_solve_assembly_success,
)
from freecad_mcp.operations.p7_assembly import (
    create_assembly_joint_operation,
    create_datum_plane_operation,
    solve_assembly_operation,
)
from tests.helpers.geometric import assert_code_compiles, assert_code_contains

_FEATURES_GUI_SOURCE = (
    Path(__file__).parents[1]
    / "addon"
    / "FreeCADMCP"
    / "rpc_server"
    / "methods"
    / "cad_methods_ops"
    / "features_gui.py"
).read_text(encoding="utf-8")


def _typed_ok(**fields):
    payload = {
        "contract_version": 1,
        "success": True,
        "ok": True,
        "outcome": "committed",
        "committed": True,
        "retry_safe": False,
        "datum_name": "CrossDatum",
        "plane_name": "CrossDatum",
        "body_name": "BodyA",
        "doc": "Doc",
        "snapshot_id": "snap-1",
        "restored_id": "snap-1",
        "from_obj": "Old",
        "to_obj": "New",
        "binder_name": "Binder",
        "source": "Src",
    }
    payload.update(fields)
    return payload


def _ok_conn(output: str = '{"ok": true}'):
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {
        "success": True,
        "message": "Python code execution scheduled. \nOutput: " + output,
        "recompute_errors": [],
    }
    conn.preview_attachment.return_value = make_preview_attachment_success("CrossDatum")
    conn.create_datum_plane.return_value = make_create_datum_plane_success("CrossDatum", "BodyA")
    conn.delete_object.return_value = make_delete_object_success(ObjectName("Body"), ["Body"])
    conn.snapshot.return_value = make_snapshot_success("snap-1", "Doc", 1)
    conn.restore.return_value = make_restore_success("snap-1", "Doc", 1)
    conn.relink_references.return_value = make_relink_references_success("Old", "New")
    conn.capture_state.return_value = make_capture_state_success(
        "Doc",
        {
            "Pad": {
                "name": "Pad",
                "placement_base": {"x": 0, "y": 0, "z": 0},
                "bbox": {"xmin": 0, "ymin": 0, "zmin": 0, "xmax": 2, "ymax": 1, "zmax": 1},
                "face_count": 6,
                "edge_count": 12,
            }
        },
    )
    conn.get_gui_state.return_value = {"active_document": "D"}
    return conn


def _fail_conn():
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {"success": False, "error": "oops"}
    conn.preview_attachment.return_value = make_preview_attachment_failure(
        "PREVIEW_ATTACHMENT_FAILED", "oops"
    )
    conn.create_datum_plane.return_value = make_create_datum_plane_failure(
        "CREATE_DATUM_PLANE_FAILED", "oops"
    )
    conn.delete_object.return_value = make_delete_object_failure("DELETE_OBJECT_FAILED", "oops")
    conn.snapshot.return_value = make_snapshot_failure("SNAPSHOT_FAILED", "oops")
    conn.restore.return_value = make_restore_failure("RESTORE_FAILED", "oops")
    conn.relink_references.return_value = make_relink_references_failure(
        "RELINK_REFERENCES_FAILED", "oops"
    )
    conn.capture_state.return_value = make_capture_state_failure("CAPTURE_STATE_FAILED", "oops")
    return conn


def _code(conn) -> str:
    return conn.execute_code.call_args[0][0]


def _text(response) -> str:
    content = response.content if hasattr(response, "content") else response
    return " ".join(item.text for item in content if isinstance(item, TextContent))


class TestPreviewAttachment:
    def test_compiles_and_inspects_datum_attachment(self):
        conn = _ok_conn()
        resp = preview_attachment_operation(conn, True, "Doc", "CrossDatum")
        assert not resp.isError
        conn.preview_attachment.assert_called_once_with("Doc", "CrossDatum")
        conn.execute_code.assert_not_called()

    def test_json_output_is_returned_directly(self):
        resp = preview_attachment_operation(_ok_conn(), True, "Doc", "CrossDatum")
        assert '"datum_name": "CrossDatum"' in _text(resp)

    def test_failure_is_surfaced(self):
        resp = preview_attachment_operation(_fail_conn(), True, "Doc", "CrossDatum")
        assert "Failed to preview attachment" in _text(resp)


class TestI2SilentBuildAssertion:
    """I2 — pad/pocket verification lives in addon GUI builders, not execute_code."""

    def test_pad_asserts_direction_parallel_to_sketch_normal(self):
        assert_code_contains(
            _FEATURES_GUI_SOURCE,
            "pad_feature_gui",
            "_build_feature_result",
            "set_feature_bool",
        )

    def test_pocket_asserts_direction_parallel_to_sketch_normal(self):
        assert_code_contains(
            _FEATURES_GUI_SOURCE,
            "pocket_feature_gui",
            "_build_feature_result",
            "set_feature_bool",
        )

    def test_pad_mismatch_failure_is_surfaced(self):
        conn = _ok_conn()
        conn.pad_feature.return_value = {"success": False, "error": "build failed"}
        resp = pad_feature_operation(conn, True, "Doc", "Profile", "MyPad", 5.0)
        assert "Failed to create pad" in _text(resp)


class TestI3RecomputeLog:
    """I3 — typed loft routes through JSON-RPC instead of execute-code."""

    def test_loft_routes_typed_rpc(self):
        conn = MagicMock()
        conn.get_active_screenshot.return_value = None
        conn.loft_feature.return_value = _typed_ok(feature="MyLoft")
        loft_feature_operation(conn, True, "Doc", ["S1", "S2"], "MyLoft")
        conn.loft_feature.assert_called_once()
        conn.execute_code.assert_not_called()


class TestPadPocketHardening:
    """Pad/Pocket typed RPC routing."""

    def test_pad_routes_typed_rpc(self):
        conn = MagicMock()
        conn.get_active_screenshot.return_value = None
        conn.pad_feature.return_value = _typed_ok(feature="MyPad", body_name="Body", tip="MyPad")
        pad_feature_operation(conn, True, "Doc", "Sketch", "MyPad", 5.0)
        conn.pad_feature.assert_called_once()
        conn.execute_code.assert_not_called()

    def test_pocket_routes_typed_rpc(self):
        conn = MagicMock()
        conn.get_active_screenshot.return_value = None
        conn.pocket_feature.return_value = _typed_ok(feature="MyPocket")
        pocket_feature_operation(conn, True, "Doc", "Sketch", "MyPocket", 3.0)
        conn.pocket_feature.assert_called_once()
        conn.execute_code.assert_not_called()

    def test_pad_has_no_document_level_fallback(self):
        assert "doc.addObject(\"PartDesign::Pad\"" not in _FEATURES_GUI_SOURCE
        assert "No PartDesign::Body found" in _FEATURES_GUI_SOURCE

    def test_pocket_has_no_document_level_fallback(self):
        assert "doc.addObject(\"PartDesign::Pocket\"" not in _FEATURES_GUI_SOURCE
        assert "No PartDesign::Body found" in _FEATURES_GUI_SOURCE

    def test_build_has_no_inner_transaction_control(self):
        assert "openTransaction" not in _FEATURES_GUI_SOURCE
        assert "commitTransaction" not in _FEATURES_GUI_SOURCE
        assert "abortTransaction" not in _FEATURES_GUI_SOURCE

    def test_runs_sketch_diagnostics_gate(self):
        assert_code_contains(
            _FEATURES_GUI_SOURCE,
            "ConflictingConstraints",
            "MalformedConstraints",
            "isClosed",
        )

    def test_verifies_body_membership_and_tip(self):
        assert_code_contains(
            _FEATURES_GUI_SOURCE, "body.Group", "body.Tip", "is not a Body member"
        )

    def test_verifies_signed_material_delta(self):
        assert_code_contains(
            _FEATURES_GUI_SOURCE,
            "volume_before_mm3",
            "volume_after_mm3",
            "material_delta_mm3",
            "ZERO_MATERIAL_DELTA",
            "MATERIAL_DELTA_DIRECTION_MISMATCH",
        )

    def test_strict_requires_explicit_body_name(self):
        assert "strict PartDesign mode requires an explicit body_name" in _FEATURES_GUI_SOURCE

    def test_non_strict_autodetects_owning_body(self):
        assert "obj.TypeId == \"PartDesign::Body\" and sketch in obj.Group" in _FEATURES_GUI_SOURCE

    def test_returns_structured_payload(self):
        conn = _ok_conn()
        conn.pad_feature.return_value = _typed_ok(
            feature="MyPad", body="Body", tip="MyPad"
        )
        resp = pad_feature_operation(conn, True, "Doc", "Sketch", "MyPad", 5.0)
        assert not resp.isError
        assert "MyPad" in _text(resp)
        conn.execute_code.assert_not_called()


class TestI4FindSubshapes:
    """I4 — find_faces/find_edges use typed RPC."""

    def test_find_faces_routes_typed_rpc(self):
        conn = MagicMock()
        conn.get_active_screenshot.return_value = None
        conn.find_faces.return_value = {"ok": True, "object": "Pad", "count": 0, "results": []}
        find_faces_operation(conn, True, "Doc", "Pad", type="Plane")
        conn.find_faces.assert_called_once()
        conn.execute_code.assert_not_called()

    def test_find_faces_returns_ranked_json(self):
        out = {
            "ok": True,
            "object": "Pad",
            "kind": "Face",
            "count": 1,
            "results": [{"sub": "Face3", "type": "Plane", "global_center": {"x": 0, "y": 0, "z": 5}, "area": 78.5}],
        }
        conn = MagicMock()
        conn.get_active_screenshot.return_value = None
        conn.find_faces.return_value = out
        resp = find_faces_operation(conn, True, "Doc", "Pad", type="Plane")
        assert "Face3" in _text(resp)

    def test_find_failure_is_surfaced(self):
        conn = MagicMock()
        conn.get_active_screenshot.return_value = None
        conn.find_faces.side_effect = RuntimeError("oops")
        resp = find_faces_operation(conn, True, "Doc", "Pad")
        assert "Failed to find faces" in _text(resp)


class TestI6CrossBodyPreflight:
    """I6 — datum/binder creation ops warn at creation time when a support lives
    in a different body with a non-identity placement (the P1 risk)."""

    def test_datum_plane_code_includes_preflight_snippet(self):
        conn = _ok_conn()
        resp = create_datum_plane_operation(
            conn, True, "Doc", "CrossDatum", "BodyA",
            mode="through_point", source_ref="Pad:Face3",
        )
        assert not resp.isError
        conn.create_datum_plane.assert_called_once()
        conn.execute_code.assert_not_called()

    def test_warning_is_surfaced_and_json_stays_clean(self):
        conn = _ok_conn()
        resp = create_datum_plane_operation(
            conn, True, "Doc", "CrossDatum", "BodyA",
            mode="through_point", source_ref="Pad:Face3",
        )
        text = _text(resp)
        assert '"plane_name": "CrossDatum"' in text
        assert "CrossDatum" in text

    def test_no_warning_when_no_risk(self):
        conn = MagicMock()
        conn.get_active_screenshot.return_value = None
        conn.create_datum_plane.return_value = make_create_datum_plane_success("P", "BodyA")
        resp = create_datum_plane_operation(
            conn, True, "Doc", "P", "BodyA", mode="through_point",
        )
        text = _text(resp)
        assert '"plane_name": "P"' in text


class TestI5DeleteObject:
    """I5 — delete_object refuses to silently orphan dependents (P6), and can
    recurse or force-delete on demand."""

    def test_refuses_when_dependents_and_lists_them(self):
        conn = _ok_conn()
        conn.delete_object.return_value = make_delete_object_failure(
            "DELETE_REFUSED",
            "Refused to delete Body: it has 1 dependent object(s): Pad (PartDesign::Pad)",
        )
        resp = delete_object_operation(conn, True, "Doc", "Body")
        text = _text(resp)
        assert "Refused" in text or "Failed" in text
        assert "Pad" in text
        assert "PartDesign::Pad" in text
        conn.delete_object.assert_called_once()
        conn.execute_code.assert_not_called()

    def test_recursive_deletes_dependents(self):
        conn = _ok_conn()
        conn.delete_object.return_value = make_delete_object_success(
            ObjectName("Body"), ["Pad", "Body"]
        )
        resp = delete_object_operation(conn, True, "Doc", "Body", recursive=True)
        text = _text(resp)
        assert "Pad" in text and "Body" in text
        assert '"deleted": ["Pad", "Body"]' in text
        conn.delete_object.assert_called_once()
        conn.execute_code.assert_not_called()

    def test_force_reports_orphans_left(self):
        conn = _ok_conn()
        conn.delete_object.return_value = make_delete_object_success(ObjectName("Body"), ["Body"])
        resp = delete_object_operation(conn, True, "Doc", "Body", force=True)
        text = _text(resp)
        assert "Body" in text
        conn.delete_object.assert_called_once()
        conn.execute_code.assert_not_called()

    def test_delete_routes_typed_rpc(self):
        conn = MagicMock()
        conn.get_active_screenshot.return_value = None
        conn.delete_object.return_value = {
            "contract_version": 1,
            "success": True,
            "ok": True,
            "outcome": "committed",
            "committed": True,
            "retry_safe": False,
            "object_name": "Body",
            "deleted": ["Pad", "Body"],
            "refused": False,
        }
        delete_object_operation(conn, True, "Doc", "Body", recursive=True)
        conn.delete_object.assert_called_once()
        conn.execute_code.assert_not_called()

    def test_typed_failure_is_surfaced_without_execute_code(self):
        conn = _ok_conn()
        conn.delete_object.return_value = make_delete_object_failure(
            "DELETE_OBJECT_FAILED",
            "rollback rejected deletion",
        )
        response = delete_object_operation(conn, True, "Doc", "Body")
        assert response.isError
        assert "rollback rejected deletion" in _text(response)
        conn.delete_object.assert_called_once()
        conn.execute_code.assert_not_called()


class TestI7SnapshotRestore:
    """I7 — snapshot/restore uses the typed addon lifecycle (P12)."""

    def test_snapshot_uses_typed_rpc(self):
        conn = _ok_conn()
        snapshot_operation(conn, True, "Doc")
        conn.snapshot.assert_called_once_with("Doc")
        conn.execute_code.assert_not_called()

    def test_restore_uses_typed_rpc_not_close_open_code(self):
        conn = _ok_conn()
        restore_operation(conn, True, "Doc", "snap-123")
        conn.restore.assert_called_once_with("Doc", "snap-123")
        conn.execute_code.assert_not_called()

    def test_snapshot_returns_json(self):
        conn = _ok_conn()
        resp = snapshot_operation(conn, True, "Doc")
        assert json.loads(_text(resp))["snapshot_id"] == "snap-1"

    def test_restore_returns_json(self):
        conn = _ok_conn()
        resp = restore_operation(conn, True, "Doc")
        assert json.loads(_text(resp))["restored_id"] == "snap-1"

    def test_snapshot_failure_is_surfaced(self):
        conn = _ok_conn()
        conn.snapshot.side_effect = RuntimeError("snapshot failed")
        resp = snapshot_operation(conn, True, "Doc")
        assert "snapshot failed" in _text(resp)

    def test_restore_failure_is_surfaced(self):
        conn = _ok_conn()
        conn.restore.side_effect = RuntimeError("restore failed")
        resp = restore_operation(conn, True, "Doc")
        assert "restore failed" in _text(resp)


class TestI9SolveAssembly:
    """I9 — solve_assembly re-solves an Assembly via the real internal solver."""

    def test_apply_helper_tries_solve_entry_points(self):
        from pathlib import Path

        code = (
            Path(__file__).resolve().parents[1]
            / "addon"
            / "FreeCADMCP"
            / "rpc_server"
            / "methods"
            / "cad_methods_ops"
            / "assembly_actions.py"
        ).read_text(encoding="utf-8")
        assert_code_compiles(code)
        assert_code_contains(
            code,
            "Assembly::AssemblyObject",
            "solveIfAllowed",
            "assembly.solve()",
        )
        assert "doc.recompute()" not in code
        assert ".recompute(" not in code

    def test_calls_typed_rpc_once_and_never_execute_code(self):
        conn = _ok_conn()
        conn.solve_assembly.return_value = make_solve_assembly_success(
            "Asm", "assembly.solve()", "0"
        )
        response = solve_assembly_operation(conn, True, "Doc", "Asm")
        assert not response.isError
        conn.solve_assembly.assert_called_once_with("Doc", "Asm")
        conn.execute_code.assert_not_called()

    def test_returns_json_with_method(self):
        conn = MagicMock()
        conn.get_active_screenshot.return_value = None
        conn.solve_assembly.return_value = make_solve_assembly_success(
            "Asm", "assembly.solve()", "0"
        )
        resp = solve_assembly_operation(conn, True, "Doc", "Asm")
        payload = json.loads(_text(resp))
        assert payload["assembly"] == "Asm"
        assert payload["method"] == "assembly.solve()"
        conn.execute_code.assert_not_called()

    def test_failure_is_surfaced(self):
        conn = MagicMock()
        conn.get_active_screenshot.return_value = None
        conn.solve_assembly.return_value = make_solve_assembly_failure(
            "SOLVE_UNAVAILABLE", "oops"
        )
        resp = solve_assembly_operation(conn, True, "Doc", "Asm")
        assert "Failed to run solve_assembly" in _text(resp)
        conn.solve_assembly.assert_called_once_with("Doc", "Asm")
        conn.execute_code.assert_not_called()


class TestM4JointPreflight:
    """M4 — create_assembly_joint is a typed mutation; preflight lives in templates only."""

    def test_joint_uses_typed_rpc(self):
        conn = MagicMock()
        conn.get_active_screenshot.return_value = None
        conn.create_assembly_joint.return_value = make_create_assembly_joint_success(
            "J", "J", "Fixed", "Asm"
        )
        create_assembly_joint_operation(conn, True, "Doc", "Asm", "Fixed", "C1", "C2")
        conn.create_assembly_joint.assert_called_once()
        conn.execute_code.assert_not_called()
        assert conn.create_assembly_joint.call_args.args[3:5] == ("C1", "C2")

    def test_joint_success_json(self):
        conn = MagicMock()
        conn.get_active_screenshot.return_value = None
        conn.create_assembly_joint.return_value = make_create_assembly_joint_success(
            "J", "J", "Fixed", "Asm"
        )
        resp = create_assembly_joint_operation(conn, True, "Doc", "Asm", "Fixed", "C1", "C2")
        payload = json.loads(_text(resp))
        assert payload["joint"] == "J"
        assert "PREFLIGHT WARNING" not in _text(resp)


class TestM6FaceNormalEdgeAxis:
    """M6 — face_normal/edge_axis typed RPC."""

    def test_face_normal_routes_typed_rpc(self):
        conn = MagicMock()
        conn.get_active_screenshot.return_value = None
        conn.face_normal.return_value = {
            "contract_version": 1,
            "success": True,
            "ok": True,
            "outcome": "observed",
            "retry_safe": False,
            "object": "Pad",
            "subshape": "Face3",
            "type": "Plane",
            "global_center": {"x": 0, "y": 0, "z": 5},
            "global_normal": {"x": 0, "y": 0, "z": 1},
        }
        face_normal_operation(conn, True, "Doc", "Pad", "Face3")
        conn.face_normal.assert_called_once_with("Doc", "Pad", "Face3")
        conn.execute_code.assert_not_called()

    def test_face_normal_returns_json(self):
        conn = MagicMock()
        conn.get_active_screenshot.return_value = None
        conn.face_normal.return_value = {
            "contract_version": 1,
            "success": True,
            "ok": True,
            "outcome": "observed",
            "retry_safe": False,
            "object": "Pad",
            "subshape": "Face3",
            "type": "Plane",
            "global_center": {"x": 0, "y": 0, "z": 5},
            "global_normal": {"x": 0, "y": 0, "z": 1},
        }
        resp = face_normal_operation(conn, True, "Doc", "Pad", "Face3")
        assert "Face3" in _text(resp)

    def test_face_normal_failure_is_surfaced(self):
        conn = MagicMock()
        conn.get_active_screenshot.return_value = None
        conn.face_normal.return_value = {
            "success": False,
            "ok": False,
            "error_code": "FACE_NORMAL_FAILED",
            "error": "oops",
        }
        resp = face_normal_operation(conn, True, "Doc", "Pad", "Face3")
        assert "Failed to run face_normal" in _text(resp) or "Failed" in _text(resp)


class TestM3PlacementAudit:
    """M3 — placement audit typed RPC."""

    def test_audit_routes_typed_rpc(self):
        conn = MagicMock()
        conn.get_active_screenshot.return_value = None
        conn.placement_audit.return_value = {"ok": True, "doc": "Doc", "bodies": []}
        placement_audit_operation(conn, True, "Doc")
        conn.placement_audit.assert_called_once_with("Doc")
        conn.execute_code.assert_not_called()

    def test_audit_returns_json(self):
        conn = MagicMock()
        conn.get_active_screenshot.return_value = None
        conn.placement_audit.return_value = {"ok": True, "doc": "Doc", "bodies": []}
        resp = placement_audit_operation(conn, True, "Doc")
        assert "Doc" in _text(resp)

    def test_audit_failure_is_surfaced(self):
        conn = MagicMock()
        conn.get_active_screenshot.return_value = None
        conn.placement_audit.side_effect = RuntimeError("oops")
        resp = placement_audit_operation(conn, True, "Doc")
        assert "Failed to audit placements" in _text(resp)


class TestM5RelinkReferences:
    """M5 — relink_references re-points all link-type properties."""

    def test_relink_code_scans_link_properties(self):
        conn = _ok_conn()
        resp = relink_references_operation(conn, True, "Doc", "Old", "New")
        assert not resp.isError
        conn.relink_references.assert_called_once_with("Doc", "Old", "New")
        conn.execute_code.assert_not_called()

    def test_relink_returns_json(self):
        resp = relink_references_operation(_ok_conn(), True, "Doc", "Old", "New")
        text = _text(resp)
        assert '"from_obj": "Old"' in text and '"to_obj": "New"' in text

    def test_relink_failure_is_surfaced(self):
        resp = relink_references_operation(_fail_conn(), True, "Doc", "Old", "New")
        assert "Failed to relink references" in _text(resp)


class TestI10StructuredDiff:
    """I10 — capture_state + geometric_diff as the P10 text-only fallback."""

    def test_capture_state_code_records_bbox_and_counts(self):
        conn = _ok_conn()
        resp = capture_state_operation(conn, True, "Doc", ["Pad"])
        assert not resp.isError
        conn.capture_state.assert_called_once_with("Doc", ["Pad"])
        conn.execute_code.assert_not_called()

    def test_capture_state_returns_json(self):
        resp = capture_state_operation(_ok_conn(), True, "Doc", ["Pad"])
        assert '"doc": "Doc"' in _text(resp)

    def test_geometric_diff_reports_changes(self):
        before = {
            "doc": "Doc",
            "objects": [
                {"name": "Pad", "placement_base": {"x": 0, "y": 0, "z": 0},
                 "placement_rotation": None,
                 "bbox": {"xmin": 0, "ymin": 0, "zmin": 0, "xmax": 1, "ymax": 1, "zmax": 1},
                 "face_count": 6, "edge_count": 12},
            ],
        }
        conn = _ok_conn()
        resp = geometric_diff_operation(conn, True, "Doc", before, ["Pad"])
        payload = json.loads(_text(resp))
        assert payload["ok"] is True
        diff = next(d for d in payload["diffs"] if d["name"] == "Pad")
        assert diff["changed"] is True
        assert diff["bbox_after"]["xmax"] == 2
        assert diff["bbox_before"]["xmax"] == 1

    def test_capture_failure_is_surfaced(self):
        resp = capture_state_operation(_fail_conn(), True, "Doc")
        assert "Failed to capture state" in _text(resp)


class TestP10GetViewFallback:
    """P10 — get_view returns ImageContent when a screenshot is available, and a
    compact geometric state (I10) when it cannot capture a viewable image."""

    def test_returns_image_content_when_screenshot_available(self):
        from mcp.types import ImageContent
        conn = MagicMock()
        conn.get_active_screenshot.return_value = "BASE64PNG"
        conn.execute_code.return_value = {"success": True, "message": "", "recompute_errors": []}
        resp = get_view_operation(conn, "Isometric")
        content = resp.content if hasattr(resp, "content") else resp
        assert any(isinstance(item, ImageContent) for item in content)

    def test_falls_back_to_structured_state_when_no_screenshot(self):
        conn = _ok_conn()
        conn.get_active_screenshot.return_value = None
        conn.get_gui_state.return_value = {"active_document": "D"}
        conn.capture_state.return_value = make_capture_state_success(
            "D",
            {
                "Pad": {
                    "name": "Pad",
                    "face_count": 6,
                }
            },
        )
        resp = get_view_operation(conn, "Isometric", focus_object="Pad")
        text = _text(resp)
        assert "Cannot get a viewable screenshot" in text
        assert "Pad" in text
        conn.capture_state.assert_called_once()

    def test_falls_back_to_message_when_capture_fails(self):
        conn = MagicMock()
        conn.get_active_screenshot.return_value = None
        conn.execute_code.return_value = {"success": False, "error": "boom"}
        resp = get_view_operation(conn, "Isometric")
        assert "Cannot get screenshot" in _text(resp)
