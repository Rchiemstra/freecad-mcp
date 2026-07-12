"""
Tests for P4 gear operations.

Layer-A: Schema / error propagation
Layer-B: Code-fragment and invariant checks
Layer-C: Analytic involute math conformance (pure Python)
Layer-D: Gear-pair compatibility
"""
from __future__ import annotations

import json
import math
from unittest.mock import MagicMock

import pytest
from mcp.types import TextContent

from freecad_mcp.operations.p4_gears import (
    check_gear_pair_operation,
    compute_gear_geometry_operation,
    create_helical_gear_operation,
    create_involute_gear_operation,
)
from tests.helpers.curves import (
    assert_involute_conformance,
    assert_on_involute_direct,
    involute_parameter_at_radius,
    involute_radius,
    involute_x,
    involute_y,
    sample_involute,
)
from tests.helpers.geometric import (
    assert_addendum_diameter,
    assert_code_compiles,
    assert_code_contains,
    assert_pitch_diameter,
)


# ---------------------------------------------------------------------------
# Test helpers (local — mirrors conftest for isolation)
# ---------------------------------------------------------------------------

def _ok_conn(output="done"):
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {"success": True, "message": output, "recompute_errors": []}
    return conn


def _fail_conn(error="oops"):
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {"success": False, "error": error}
    return conn


def _code(conn) -> str:
    return conn.execute_code.call_args[0][0]


def _text(response) -> str:
    content = response.content if hasattr(response, "content") else response
    return " ".join(item.text for item in content if isinstance(item, TextContent))


# ---------------------------------------------------------------------------
# Layer-A: Schema / error propagation
# ---------------------------------------------------------------------------

class TestCreateInvoluteGearLayerA:
    def test_success_response_contains_name(self):
        conn = _ok_conn()
        resp = create_involute_gear_operation(conn, True, "Doc", "Gear1", 20, 2.0, 10.0)
        assert _text(resp)

    def test_failure_propagates_error(self):
        conn = _fail_conn("execute failed")
        resp = create_involute_gear_operation(conn, True, "Doc", "Gear1", 20, 2.0, 10.0)
        assert "execute failed" in _text(resp) or "Failed" in _text(resp)

    def test_execute_code_called_once(self):
        conn = _ok_conn()
        create_involute_gear_operation(conn, True, "Doc", "Gear1", 20, 2.0, 10.0)
        conn.execute_code.assert_called_once()

    def test_no_screenshot_when_text_only(self):
        conn = _ok_conn()
        from mcp.types import ImageContent
        resp = create_involute_gear_operation(conn, True, "Doc", "Gear1", 20, 2.0, 10.0)
        assert not any(isinstance(i, ImageContent) for i in resp)


class TestComputeGearGeometryLayerA:
    def test_returns_text_with_json(self):
        conn = MagicMock()
        resp = compute_gear_geometry_operation(conn, True, 20, 2.0, 20.0)
        text = _text(resp)
        data = json.loads(text)
        assert data["teeth"] == 20
        assert data["module"] == 2.0

    def test_no_freecad_call(self):
        conn = MagicMock()
        compute_gear_geometry_operation(conn, True, 20, 2.0)
        conn.execute_code.assert_not_called()

    def test_pressure_angle_field(self):
        conn = MagicMock()
        resp = compute_gear_geometry_operation(conn, True, 30, 1.5, pressure_angle=14.5)
        data = json.loads(_text(resp))
        assert data["pressure_angle"] == 14.5


class TestCheckGearPairLayerA:
    def test_same_module_meshes(self):
        conn = MagicMock()
        resp = check_gear_pair_operation(conn, True, 20, 2.0, 40, 2.0)
        data = json.loads(_text(resp))
        assert data["meshes"] is True

    def test_different_module_no_mesh(self):
        conn = MagicMock()
        resp = check_gear_pair_operation(conn, True, 20, 2.0, 40, 1.5)
        data = json.loads(_text(resp))
        assert data["meshes"] is False

    def test_gear_ratio_computed(self):
        conn = MagicMock()
        resp = check_gear_pair_operation(conn, True, 20, 2.0, 40, 2.0)
        data = json.loads(_text(resp))
        assert abs(data["gear_ratio"] - 2.0) < 1e-6

    def test_center_distance_note_when_wrong(self):
        conn = MagicMock()
        resp = check_gear_pair_operation(conn, True, 20, 2.0, 20, 2.0, center_distance=999.0)
        data = json.loads(_text(resp))
        assert len(data["notes"]) > 0

    def test_no_freecad_call(self):
        conn = MagicMock()
        check_gear_pair_operation(conn, True, 20, 2.0, 40, 2.0)
        conn.execute_code.assert_not_called()


# ---------------------------------------------------------------------------
# Layer-B: Code fragments and structural invariants
# ---------------------------------------------------------------------------

class TestCreateInvoluteGearLayerB:
    def _gear_code(self, teeth=20, module=2.0, width=10.0, **kw):
        conn = _ok_conn()
        create_involute_gear_operation(conn, True, "Doc", "Gear1", teeth, module, width, **kw)
        return _code(conn)

    def test_compiles(self):
        assert_code_compiles(self._gear_code())

    def test_involute_formula_present(self):
        code = self._gear_code()
        assert_code_contains(code, "math.cos(t)", "math.sin(t)", "_base_radius")

    def test_teeth_injected(self):
        code = self._gear_code(teeth=17)
        assert_code_contains(code, "17")

    def test_module_injected(self):
        code = self._gear_code(module=3.0)
        assert_code_contains(code, "3.0")

    def test_pressure_angle_converted_to_radians(self):
        code = self._gear_code(pressure_angle=20.0)
        assert_code_contains(code, "math.radians")

    def test_has_undercut_branch(self):
        code = self._gear_code()
        assert_code_contains(code, "_has_undercut")

    def test_tip_arc_present(self):
        code = self._gear_code()
        assert_code_contains(code, "_tip_steps", "_r_tip_ang")

    def test_root_arc_present(self):
        code = self._gear_code()
        assert_code_contains(code, "_root_steps", "_arc_start")

    def test_profile_to_sketch_code_present(self):
        code = self._gear_code()
        assert_code_contains(code, "Part.LineSegment", "Coincident")

    def test_construction_circles_present(self):
        code = self._gear_code()
        assert_code_contains(code, "RootRadius", "PitchRadius", "OuterRadius", "BaseRadius")

    def test_pad_feature_created(self):
        code = self._gear_code()
        assert_code_contains(code, "PartDesign::Pad")

    def test_bore_code_present_when_specified(self):
        code = self._gear_code(bore_diameter=5.0)
        assert_code_contains(code, "5.0")

    def test_body_creation_present(self):
        code = self._gear_code()
        assert_code_contains(code, "PartDesign::Body")

    def test_recompute_called(self):
        code = self._gear_code()
        assert_code_contains(code, "_doc.recompute()")

    def test_doc_lookup_present(self):
        code = self._gear_code()
        assert_code_contains(code, "FreeCAD.getDocument")


class TestCreateHelicalGearLayerB:
    def _gear_code(self, teeth=20, module=2.0, width=15.0, helix_angle=15.0):
        conn = _ok_conn()
        create_helical_gear_operation(conn, True, "Doc", "HelGear", teeth, module, width,
                                      helix_angle=helix_angle)
        return _code(conn)

    def test_compiles(self):
        assert_code_compiles(self._gear_code())

    def test_helix_feature_present(self):
        code = self._gear_code()
        assert_code_contains(code, "PartDesign::AdditiveHelix")

    def test_pitch_computed(self):
        code = self._gear_code()
        assert_code_contains(code, "_helix_pitch")

    def test_involute_formula_present(self):
        code = self._gear_code()
        assert_code_contains(code, "_ix", "_iy", "_polar")


# ---------------------------------------------------------------------------
# Layer-C: Analytic involute math conformance
# ---------------------------------------------------------------------------

class TestInvoluteMathLayerC:
    """Verify the involute helper functions are analytically correct."""

    def test_involute_x_at_zero(self):
        r_b = 10.0
        assert abs(involute_x(r_b, 0.0) - r_b) < 1e-12

    def test_involute_y_at_zero(self):
        r_b = 10.0
        assert abs(involute_y(r_b, 0.0)) < 1e-12

    def test_radius_formula(self):
        r_b = 10.0
        for t in [0.0, 0.2, 0.5, 1.0, 1.5]:
            r = involute_radius(r_b, t)
            x = involute_x(r_b, t)
            y = involute_y(r_b, t)
            assert abs(math.hypot(x, y) - r) < 1e-10

    def test_radius_monotone_increasing(self):
        r_b = 10.0
        ts = [i * 0.1 for i in range(20)]
        radii = [involute_radius(r_b, t) for t in ts]
        for i in range(1, len(radii)):
            assert radii[i] >= radii[i - 1] - 1e-10

    def test_parameter_at_radius_roundtrip(self):
        r_b = 10.0
        for r in [11.0, 12.0, 15.0, 20.0]:
            t = involute_parameter_at_radius(r_b, r)
            assert abs(involute_radius(r_b, t) - r) < 1e-10

    def test_parameter_at_base_radius_is_zero(self):
        r_b = 10.0
        t = involute_parameter_at_radius(r_b, r_b)
        assert abs(t) < 1e-10

    def test_sample_involute_length(self):
        pts = sample_involute(10.0, 0.0, 1.0, 50)
        assert len(pts) == 50

    def test_sample_involute_all_on_curve(self):
        r_b = 8.0
        pts = sample_involute(r_b, 0.0, 1.2, 30)
        assert_on_involute_direct(pts, r_b)

    def test_tip_radius_correct_for_20t_m2(self):
        teeth, module = 20, 2.0
        r_pitch = module * teeth / 2.0
        r_outer = r_pitch + module
        assert abs(r_outer - 22.0) < 1e-10

    def test_base_radius_correct_for_20pa(self):
        teeth, module = 20, 2.0
        alpha = math.radians(20.0)
        r_pitch = module * teeth / 2.0
        r_base = r_pitch * math.cos(alpha)
        assert abs(r_base - 20 * math.cos(math.radians(20))) < 1e-10

    def test_inv_function_at_20_degrees(self):
        alpha = math.radians(20.0)
        inv_a = math.tan(alpha) - alpha
        assert abs(inv_a - 0.014904) < 1e-5


class TestComputeGearGeometryLayerC:
    """Verify analytic values returned by compute_gear_geometry_operation."""

    def _geom(self, teeth, module, pa=20.0, **kw):
        conn = MagicMock()
        resp = compute_gear_geometry_operation(conn, True, teeth, module, pa, **kw)
        return json.loads(_text(resp))

    def test_pitch_diameter(self):
        d = self._geom(20, 2.0)
        assert_pitch_diameter(20, 2.0, d["pitch_dia"])

    def test_addendum_diameter(self):
        d = self._geom(20, 2.0)
        assert_addendum_diameter(20, 2.0, d["addendum_dia"])

    def test_base_diameter_formula(self):
        d = self._geom(20, 2.0, pa=20.0)
        expected = 20 * 2.0 * math.cos(math.radians(20.0))
        assert abs(d["base_dia"] - expected) < 1e-4

    def test_circular_pitch(self):
        d = self._geom(20, 2.0)
        assert abs(d["circular_pitch"] - math.pi * 2.0) < 1e-5

    def test_base_pitch(self):
        d = self._geom(20, 2.0, pa=20.0)
        expected = math.pi * 2.0 * math.cos(math.radians(20.0))
        assert abs(d["base_pitch"] - expected) < 1e-5

    def test_addendum_equals_module(self):
        d = self._geom(20, 2.0)
        assert abs(d["addendum"] - 2.0) < 1e-10

    def test_involute_fn_positive(self):
        d = self._geom(20, 2.0)
        assert d["involute_fn"] > 0

    def test_root_diameter_less_than_pitch(self):
        d = self._geom(20, 2.0)
        assert d["root_dia"] < d["pitch_dia"]

    def test_addendum_greater_than_pitch(self):
        d = self._geom(20, 2.0)
        assert d["addendum_dia"] > d["pitch_dia"]

    def test_helix_angle_field_stored(self):
        d = self._geom(20, 2.0, helix_angle=15.0)
        assert d["helix_angle"] == 15.0


# ---------------------------------------------------------------------------
# Layer-D: Gear-pair compatibility
# ---------------------------------------------------------------------------

class TestCheckGearPairLayerD:
    def _pair(self, t1, m1, t2, m2, **kw):
        conn = MagicMock()
        resp = check_gear_pair_operation(conn, True, t1, m1, t2, m2, **kw)
        return json.loads(_text(resp))

    def test_center_distance_theoretical(self):
        d = self._pair(20, 2.0, 40, 2.0)
        expected = 20 * 2.0 / 2 + 40 * 2.0 / 2
        assert abs(d["theoretical_cd_mm"] - expected) < 1e-5

    def test_correct_center_distance_no_note(self):
        theo = 20 * 2.0 / 2 + 40 * 2.0 / 2
        d = self._pair(20, 2.0, 40, 2.0, center_distance=theo)
        assert all("Center distance" not in n for n in d["notes"])

    def test_unit_ratio(self):
        d = self._pair(20, 2.0, 20, 2.0)
        assert abs(d["gear_ratio"] - 1.0) < 1e-6

    def test_reduction_ratio(self):
        d = self._pair(15, 2.0, 60, 2.0)
        assert abs(d["gear_ratio"] - 4.0) < 1e-6

    def test_pitch_diameters_correct(self):
        d = self._pair(20, 2.0, 40, 2.0)
        assert abs(d["pitch_dia_1"] - 40.0) < 1e-5
        assert abs(d["pitch_dia_2"] - 80.0) < 1e-5

    def test_module_mismatch_note(self):
        d = self._pair(20, 2.0, 40, 1.5)
        assert any("Module mismatch" in n for n in d["notes"])
