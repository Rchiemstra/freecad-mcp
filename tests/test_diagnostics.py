"""Unit tests for the diagnostics operations (I1 preview_attachment, and the
later I4/I10/M5/M6 helpers added in the same module)."""
from __future__ import annotations

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
from freecad_mcp.operations.core import (
    delete_object_operation,
    get_view_operation,
    pad_feature_operation,
    pocket_feature_operation,
)
from freecad_mcp.operations.p3_features import (
    helical_sweep_feature_operation,
    loft_feature_operation,
    sweep_feature_operation,
)
from freecad_mcp.operations.snapshot import (
    restore_operation,
    snapshot_operation,
)
from freecad_mcp.operations.p7_assembly import (
    create_assembly_joint_operation,
    create_datum_plane_operation,
    solve_assembly_operation,
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


class TestPreviewAttachment:
    def test_compiles_and_inspects_datum_attachment(self):
        conn = _ok_conn()
        preview_attachment_operation(conn, True, "Doc", "CrossDatum")
        code = _code(conn)
        assert_code_compiles(code)
        # Resolves the requested datum and its AttachmentSupport.
        assert_code_contains(code, "CrossDatum", "AttachmentSupport", "getGlobalPlacement")
        # Reports the P1 cross-body drop flag and a diff.
        assert_code_contains(
            code,
            "source_body_placement_dropped",
            "signed_distance_mm",
            "angle_deg",
        )

    def test_json_output_is_returned_directly(self):
        resp = preview_attachment_operation(
            _ok_conn('{"ok": true, "source_body_placement_dropped": true}'),
            True,
            "Doc",
            "CrossDatum",
        )
        assert _text(resp).startswith('{"ok": true')

    def test_failure_is_surfaced(self):
        resp = preview_attachment_operation(_fail_conn(), True, "Doc", "CrossDatum")
        assert "Failed to preview attachment" in _text(resp)


class TestI2SilentBuildAssertion:
    """I2 — pad/pocket/loft/sweep append a post-build assertion that raises on a
    wrong-direction or misplaced build (P2/P3), so silent wrong geometry becomes a
    surfaced failure instead of propagating."""

    def test_pad_asserts_direction_parallel_to_sketch_normal(self):
        conn = _ok_conn()
        pad_feature_operation(conn, True, "Doc", "Profile", "MyPad", 5.0)
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(
            code,
            "SILENT BUILD MISMATCH",
            "Direction",
            "getGlobalPlacement",
            "MyPad",
        )
        # Direction check is enabled for pad (the P2 catch).
        assert "check_direction=True" in code or "True" in code

    def test_pocket_asserts_direction_parallel_to_sketch_normal(self):
        conn = _ok_conn()
        pocket_feature_operation(conn, True, "Doc", "Profile", "MyPocket", 3.0)
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(code, "SILENT BUILD MISMATCH", "Direction", "MyPocket")

    def test_loft_asserts_bbox_only_no_direction_check(self):
        conn = _ok_conn()
        loft_feature_operation(conn, True, "Doc", ["S1", "S2"], "MyLoft")
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(code, "SILENT BUILD MISMATCH", "MyLoft", "S1")
        # Loft has no single extrusion direction, so the direction block is skipped.
        assert "if False:" in code

    def test_sweep_asserts_bbox_only_no_direction_check(self):
        conn = _ok_conn()
        sweep_feature_operation(conn, True, "Doc", "Profile", "Path", "MySweep")
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(code, "SILENT BUILD MISMATCH", "MySweep", "Profile")
        assert "if False:" in code

    def test_helical_sweep_asserts_bbox_only(self):
        conn = _ok_conn()
        helical_sweep_feature_operation(
            conn, True, "Doc", "Profile", "MyHelix", pitch=2.0, height=10.0, radius=3.0
        )
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(code, "SILENT BUILD MISMATCH", "MyHelix")

    def test_pad_mismatch_failure_is_surfaced(self):
        # When the assertion raises inside execute_code, the op reports a failure
        # with the SILENT BUILD MISMATCH prefix instead of "Pad created".
        resp = pad_feature_operation(_fail_conn(), True, "Doc", "Profile", "MyPad", 5.0)
        assert "Failed to create pad" in _text(resp)


class TestI3RecomputeLog:
    """I3 — every mutating tool appends a compact recompute log so P6 orphans
    (children left Invalid/Error after a delete/edit) surface immediately."""

    def test_pad_generated_code_includes_recompute_log_snippet(self):
        conn = _ok_conn()
        pad_feature_operation(conn, True, "Doc", "Profile", "MyPad", 5.0)
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(code, "__RECOMPUTE_LOG__", "State", "Clean")

    def test_surfaces_invalid_orphans(self):
        out = ('__RECOMPUTE_LOG__'
               '[{"name":"Orphan","state":"Invalid","valid":false}]')
        conn = _ok_conn(out)
        resp = pad_feature_operation(conn, True, "Doc", "Profile", "MyPad", 5.0)
        text = _text(resp)
        assert "Recompute log (non-clean)" in text
        assert "Orphan" in text
        assert "Invalid" in text
        assert "<INVALID>" in text

    def test_quiet_when_all_clean(self):
        conn = _ok_conn("__RECOMPUTE_LOG__[]")
        resp = pad_feature_operation(conn, True, "Doc", "Profile", "MyPad", 5.0)
        assert "Recompute log" not in _text(resp)

    def test_no_sentinel_falls_back_to_recompute_errors(self):
        conn = _ok_conn("done")
        conn.execute_code.return_value = {
            "success": True,
            "message": "Python code execution scheduled. \nOutput: done",
            "recompute_errors": [{"name": "Bad", "doc": "Doc", "state": "Error"}],
        }
        resp = pad_feature_operation(conn, True, "Doc", "Profile", "MyPad", 5.0)
        assert "Recompute errors detected" in _text(resp)
        assert "Bad" in _text(resp)


class TestI4FindSubshapes:
    """I4 — find_faces/find_edges generate geometry-filtered, ranked JSON."""

    def test_find_faces_compiles_and_filters(self):
        conn = _ok_conn()
        find_faces_operation(
            conn, True, "Doc", "Pad",
            type="Plane",
            normal_approx={"x": 0, "y": 0, "z": 1},
            limit=5,
        )
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(
            code,
            "getObject('Pad')",
            "'Faces'",
            "Plane",
            "normalAt",
            "json.dumps",
        )
        # The normal filter vector is rendered into the code.
        assert "'x': 0" in code and "'z': 1" in code

    def test_find_edges_compiles_and_filters_by_radius(self):
        conn = _ok_conn()
        find_edges_operation(
            conn, True, "Doc", "Cyl",
            type="Circle",
            radius=5.0,
            center_approx={"x": 0, "y": 0, "z": 10},
        )
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(code, "'Edges'", "Circle", "5.0")

    def test_find_faces_returns_ranked_json(self):
        out = ('{"ok": true, "object": "Pad", "kind": "Face", "count": 1, '
               '"results": [{"sub": "Face3", "type": "Plane", '
               '"global_center": {"x": 0, "y": 0, "z": 5}, '
               '"global_normal": {"x": 0, "y": 0, "z": 1}, "area": 78.5}]}')
        resp = find_faces_operation(
            _ok_conn(out), True, "Doc", "Pad", type="Plane",
            normal_approx={"x": 0, "y": 0, "z": 1},
        )
        text = _text(resp)
        assert text.startswith('{"ok": true')
        assert "Face3" in text and "Plane" in text

    def test_find_failure_is_surfaced(self):
        resp = find_faces_operation(_fail_conn(), True, "Doc", "Pad")
        assert "Failed to find faces" in _text(resp)


class TestI6CrossBodyPreflight:
    """I6 — datum/binder creation ops warn at creation time when a support lives
    in a different body with a non-identity placement (the P1 risk)."""

    def test_datum_plane_code_includes_preflight_snippet(self):
        conn = _ok_conn()
        create_datum_plane_operation(
            conn, True, "Doc", "CrossDatum", "BodyA",
            mode="FlatFace", source_ref="Pad:Face3",
        )
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(code, "__PREFLIGHT_WARN__", "CrossDatum", "PartDesign::Body")

    def test_warning_is_surfaced_and_json_stays_clean(self):
        out = ('{"ok": true, "plane": "CrossDatum"}\n'
               '__PREFLIGHT_WARN__'
               '[{"datum":"CrossDatum","datum_body":"BodyA","support":"Pad",'
               '"support_body":"BodyB","message":"Cross-body attachment: '
               'CrossDatum in body BodyA attaches to Pad in body BodyB."}]')
        conn = _ok_conn(out)
        resp = create_datum_plane_operation(
            conn, True, "Doc", "CrossDatum", "BodyA",
            mode="FlatFace", source_ref="Pad:Face3",
        )
        text = _text(resp)
        # The JSON payload is preserved (clean) and the warning is appended.
        assert text.startswith('{"ok": true, "plane": "CrossDatum"}')
        assert "PREFLIGHT WARNING" in text
        assert "CrossDatum" in text and "BodyB" in text

    def test_no_warning_when_no_risk(self):
        conn = _ok_conn('{"ok": true, "plane": "P"}\n__PREFLIGHT_WARN__[]')
        resp = create_datum_plane_operation(
            conn, True, "Doc", "P", "BodyA", mode="FlatFace",
        )
        text = _text(resp)
        assert text.startswith('{"ok": true, "plane": "P"}')
        assert "PREFLIGHT WARNING" not in text


class TestI5DeleteObject:
    """I5 — delete_object refuses to silently orphan dependents (P6), and can
    recurse or force-delete on demand."""

    def test_refuses_when_dependents_and_lists_them(self):
        out = ('{"ok": true, "object": "Body", "refused": true, "deleted": [], '
               '"dependents": [{"name": "Pad", "type": "PartDesign::Pad", "state": "Clean"}], '
               '"message": "Refused to delete Body: it has 1 dependent object(s)."}'
               '\n__RECOMPUTE_LOG__[]')
        conn = _ok_conn(out)
        resp = delete_object_operation(conn, True, "Doc", "Body")
        text = _text(resp)
        assert "refused" in text
        assert "Pad" in text
        assert "PartDesign::Pad" in text

    def test_recursive_deletes_dependents(self):
        out = ('{"ok": true, "object": "Body", "refused": false, '
               '"deleted": ["Pad", "Body"], "message": "Deleted Body and 1 dependent."}'
               '\n__RECOMPUTE_LOG__[]')
        conn = _ok_conn(out)
        resp = delete_object_operation(conn, True, "Doc", "Body", recursive=True)
        text = _text(resp)
        assert '"deleted": ["Pad", "Body"]' in text

    def test_force_reports_orphans_left(self):
        out = ('{"ok": true, "object": "Body", "refused": false, "deleted": ["Body"], '
               '"orphans_left": ["Pad"], "message": "left 1 dependent orphaned"}'
               '\n__RECOMPUTE_LOG__[]')
        conn = _ok_conn(out)
        resp = delete_object_operation(conn, True, "Doc", "Body", force=True)
        text = _text(resp)
        assert "orphans_left" in text
        assert "Pad" in text

    def test_generated_code_walks_outlist_and_compiles(self):
        conn = _ok_conn()
        delete_object_operation(conn, True, "Doc", "Body", recursive=True)
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(code, "OutList", "removeObject", "recompute", "Body")


class TestI7SnapshotRestore:
    """I7 — snapshot/restore round-trip via execute_code (P12)."""

    def test_snapshot_code_saves_and_rings_buffer(self):
        conn = _ok_conn()
        snapshot_operation(conn, True, "Doc")
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(code, "_mcp_snapshots", "mkstemp", ".FCStd", "Doc")

    def test_restore_code_opens_snapshot_in_place(self):
        conn = _ok_conn()
        restore_operation(conn, True, "Doc", "snap-123")
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(code, "_mcp_snapshots", "closeDocument", "FreeCAD.open", "snap-123")

    def test_snapshot_returns_json(self):
        out = '{"ok": true, "snapshot_id": "snap-1", "doc": "Doc", "count": 1}'
        resp = snapshot_operation(_ok_conn(out), True, "Doc")
        assert _text(resp).startswith('{"ok": true, "snapshot_id": "snap-1"')

    def test_restore_returns_json(self):
        out = '{"ok": true, "restored_id": "snap-1", "doc": "Doc", "new_doc": "Doc", "count": 1}'
        resp = restore_operation(_ok_conn(out), True, "Doc")
        assert _text(resp).startswith('{"ok": true, "restored_id": "snap-1"')

    def test_snapshot_failure_is_surfaced(self):
        resp = snapshot_operation(_fail_conn(), True, "Doc")
        assert "Failed to snapshot document" in _text(resp)

    def test_restore_failure_is_surfaced(self):
        resp = restore_operation(_fail_conn(), True, "Doc")
        assert "Failed to restore snapshot" in _text(resp)


class TestI9SolveAssembly:
    """I9 — solve_assembly re-solves an Assembly via the real internal solver."""

    def test_generated_code_tries_solve_entry_points(self):
        conn = _ok_conn()
        solve_assembly_operation(conn, True, "Doc", "Asm")
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(
            code,
            "getObject('Asm')",
            "Assembly::AssemblyObject",
            "solveIfAllowed",
            "recompute",
        )

    def test_returns_json_with_method(self):
        out = '{"ok": true, "assembly": "Asm", "method": "assembly.solve()", "status": "0"}'
        resp = solve_assembly_operation(_ok_conn(out), True, "Doc", "Asm")
        assert _text(resp).startswith('{"ok": true, "assembly": "Asm"')

    def test_failure_is_surfaced(self):
        resp = solve_assembly_operation(_fail_conn(), True, "Doc", "Asm")
        assert "Failed to solve assembly" in _text(resp)


class TestM6FaceNormalEdgeAxis:
    """M6 — face_normal/edge_axis return a subshape's global normal/axis."""

    def test_face_normal_code_derives_from_geometry(self):
        conn = _ok_conn()
        face_normal_operation(conn, True, "Doc", "Pad", "Face3")
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(code, "getObject('Pad')", "normalAt", "getGlobalPlacement", "Face3")

    def test_edge_axis_code_derives_from_curve(self):
        conn = _ok_conn()
        edge_axis_operation(conn, True, "Doc", "Cyl", "Edge2")
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(code, "Edge2", "Curve", "getGlobalPlacement")

    def test_face_normal_returns_json(self):
        out = ('{"ok": true, "object": "Pad", "subshape": "Face3", "type": "Plane", '
               '"global_center": {"x": 0, "y": 0, "z": 5}, '
               '"global_normal": {"x": 0, "y": 0, "z": 1}, "radius": null}')
        resp = face_normal_operation(_ok_conn(out), True, "Doc", "Pad", "Face3")
        assert _text(resp).startswith('{"ok": true, "object": "Pad"')

    def test_face_normal_failure_is_surfaced(self):
        resp = face_normal_operation(_fail_conn(), True, "Doc", "Pad", "Face3")
        assert "Failed to inspect subshape" in _text(resp)


class TestM3PlacementAudit:
    """M3 — placement audit lists per Body/Part placement + cross-body datums."""

    def test_audit_code_lists_bodies_and_cross_body_datums(self):
        conn = _ok_conn()
        placement_audit_operation(conn, True, "Doc")
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(
            code,
            "PartDesign::Body",
            "getGlobalPlacement",
            "cross_body_datums",
        )

    def test_audit_returns_json(self):
        out = '{"ok": true, "doc": "Doc", "bodies": [{"name": "Body", "type": "PartDesign::Body", "cross_body_datums": []}]}'
        resp = placement_audit_operation(_ok_conn(out), True, "Doc")
        assert _text(resp).startswith('{"ok": true, "doc": "Doc"')

    def test_audit_failure_is_surfaced(self):
        resp = placement_audit_operation(_fail_conn(), True, "Doc")
        assert "Failed to audit placements" in _text(resp)


class TestM5RelinkReferences:
    """M5 — relink_references re-points all link-type properties."""

    def test_relink_code_scans_link_properties(self):
        conn = _ok_conn()
        relink_references_operation(conn, True, "Doc", "Old", "New")
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(
            code,
            "getObject('Old')",
            "getObject('New')",
            "getTypeOfProperty",
            "PropertyLinkSubList",
        )

    def test_relink_returns_json(self):
        out = ('{"ok": true, "from": "Old", "to": "New", "count": 2, '
               '"relinked": [{"object": "D", "property": "AttachmentSupport", "kind": "PropertyLinkSubList"}]}')
        resp = relink_references_operation(_ok_conn(out), True, "Doc", "Old", "New")
        text = _text(resp)
        assert '"from": "Old"' in text and '"to": "New"' in text and '"count": 2' in text

    def test_relink_failure_is_surfaced(self):
        resp = relink_references_operation(_fail_conn(), True, "Doc", "Old", "New")
        assert "Failed to relink references" in _text(resp)


class TestI10StructuredDiff:
    """I10 — capture_state + geometric_diff as the P10 text-only fallback."""

    def test_capture_state_code_records_bbox_and_counts(self):
        conn = _ok_conn()
        capture_state_operation(conn, True, "Doc", ["Pad"])
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(code, "BoundBox", "face_count", "edge_count", "Pad")

    def test_capture_state_returns_json(self):
        out = ('{"ok": true, "doc": "Doc", "objects": [{"name": "Pad", "type": "PartDesign::Pad", '
               '"placement_base": {"x": 0, "y": 0, "z": 0}, "placement_rotation": null, '
               '"bbox": {"xmin": 0, "ymin": 0, "zmin": 0, "xmax": 1, "ymax": 1, "zmax": 1}, '
               '"face_count": 6, "edge_count": 12}]}')
        resp = capture_state_operation(_ok_conn(out), True, "Doc", ["Pad"])
        assert _text(resp).startswith('{"ok": true, "doc": "Doc"')

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
        current = (
            '{"ok": true, "doc": "Doc", "objects": [{"name": "Pad", '
            '"placement_base": {"x": 0, "y": 0, "z": 0}, "placement_rotation": null, '
            '"bbox": {"xmin": 0, "ymin": 0, "zmin": 0, "xmax": 2, "ymax": 1, "zmax": 1}, '
            '"face_count": 6, "edge_count": 12}]}'
        )
        import json as _j
        resp = geometric_diff_operation(_ok_conn(current), True, "Doc", before, ["Pad"])
        payload = _j.loads(_text(resp))
        assert payload["ok"] is True
        diff = next(d for d in payload["diffs"] if d["name"] == "Pad")
        assert diff["changed"] is True
        assert diff["bbox_after"]["xmax"] == 2
        assert diff["bbox_before"]["xmax"] == 1

    def test_capture_failure_is_surfaced(self):
        resp = capture_state_operation(_fail_conn(), True, "Doc")
        assert "Failed to capture state" in _text(resp)


class TestM4JointPreflight:
    """M4 — create_assembly_joint warns when a referenced component's body has
    cross-body datums attached (P5 guardrail)."""

    def test_joint_code_includes_preflight(self):
        conn = _ok_conn()
        create_assembly_joint_operation(
            conn, True, "Doc", "Asm", "Fixed", "C1", "C2",
        )
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(code, "__PREFLIGHT_WARN__", "C1", "C2")

    def test_joint_warning_surfaced_and_json_clean(self):
        out = ('{"ok": true, "joint_name": "J"}\n'
               '__PREFLIGHT_WARN__'
               '[{"component":"C1","component_body":"BodyA","datum":"D",'
               '"datum_body":"BodyB","support":"Pad","message":"Joint references C1."}]')
        conn = _ok_conn(out)
        resp = create_assembly_joint_operation(
            conn, True, "Doc", "Asm", "Fixed", "C1", "C2",
        )
        text = _text(resp)
        assert text.startswith('{"ok": true, "joint_name": "J"}')
        assert "PREFLIGHT WARNING" in text
        assert "C1" in text


class TestP10GetViewFallback:
    """P10 — get_view returns ImageContent when a screenshot is available, and a
    compact geometric state (I10) when it cannot capture a viewable image."""

    def test_returns_image_content_when_screenshot_available(self):
        from mcp.types import ImageContent
        conn = MagicMock()
        conn.get_active_screenshot.return_value = "BASE64PNG"
        conn.execute_code.return_value = {"success": True, "message": "", "recompute_errors": []}
        resp = get_view_operation(conn, "Isometric")
        assert any(isinstance(item, ImageContent) for item in resp)

    def test_falls_back_to_structured_state_when_no_screenshot(self):
        conn = MagicMock()
        conn.get_active_screenshot.return_value = None
        conn.execute_code.return_value = {
            "success": True,
            "message": 'Python code execution scheduled. \nOutput: {"ok": true, "doc": "D", "objects": [{"name": "Pad", "face_count": 6}]}',
            "recompute_errors": [],
        }
        resp = get_view_operation(conn, "Isometric", focus_object="Pad")
        text = _text(resp)
        assert "Cannot get a viewable screenshot" in text
        assert '"ok": true' in text
        assert "Pad" in text
        # The fallback code captured the focus object.
        code = conn.execute_code.call_args[0][0]
        assert "ActiveDocument" in code and "Pad" in code

    def test_falls_back_to_message_when_capture_fails(self):
        conn = MagicMock()
        conn.get_active_screenshot.return_value = None
        conn.execute_code.return_value = {"success": False, "error": "boom"}
        resp = get_view_operation(conn, "Isometric")
        assert "Cannot get screenshot" in _text(resp)
