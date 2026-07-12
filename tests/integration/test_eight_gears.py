"""
Integration smoke tests for 8 gear types.

These tests verify that each gear generator produces valid Python code
and that the computed geometry values satisfy basic invariants.
All 8 types use the same correct involute profile; some are marked
xfail until the specific extrusion strategy is confirmed working in FreeCAD.

Run against a live FreeCAD instance to get full geometric validation.
Mock-based runs only check code structure and analytic geometry values.
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
    sample_involute,
)
from tests.helpers.geometric import (
    assert_addendum_diameter,
    assert_code_compiles,
    assert_code_contains,
    assert_pitch_diameter,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _ok_conn():
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {"success": True, "message": "ok", "recompute_errors": []}
    return conn


def _code(conn) -> str:
    return conn.execute_code.call_args[0][0]


def _text(response) -> str:
    content = response.content if hasattr(response, "content") else response
    return " ".join(item.text for item in content if isinstance(item, TextContent))


def _geom(teeth, module, pa=20.0, **kw):
    conn = MagicMock()
    resp = compute_gear_geometry_operation(conn, True, teeth, module, pa, **kw)
    return json.loads(_text(resp))


# ---------------------------------------------------------------------------
# Parametric gear test cases
# ---------------------------------------------------------------------------

GEAR_CASES = [
    # (id, teeth, module, width, pressure_angle, bore, helix_angle)
    ("small_fine",       10, 1.0, 5.0,  20.0, 0.0, 0.0),
    ("standard_20t",     20, 2.0, 10.0, 20.0, 0.0, 0.0),
    ("coarse_30t",       30, 3.0, 20.0, 20.0, 0.0, 0.0),
    ("high_pa_25deg",    20, 2.0, 10.0, 25.0, 0.0, 0.0),
    ("low_pa_14_5deg",   20, 2.0, 10.0, 14.5, 0.0, 0.0),
    ("with_bore",        20, 2.0, 10.0, 20.0, 8.0, 0.0),
    ("helical_15deg",    20, 2.0, 15.0, 20.0, 0.0, 15.0),
    ("helical_30deg",    20, 2.0, 15.0, 20.0, 0.0, 30.0),
]


class TestEightGearCodes:
    """Layer-A+B: All 8 gear types produce compilable, correct-fragment code."""

    @pytest.mark.parametrize("gear_id,teeth,module,width,pa,bore,helix", GEAR_CASES)
    def test_compiles(self, gear_id, teeth, module, width, pa, bore, helix):
        conn = _ok_conn()
        if helix > 0:
            create_helical_gear_operation(
                conn, True, "Doc", gear_id, teeth, module, width,
                helix_angle=helix, pressure_angle=pa, bore_diameter=bore,
            )
        else:
            create_involute_gear_operation(
                conn, True, "Doc", gear_id, teeth, module, width,
                pressure_angle=pa, bore_diameter=bore,
            )
        assert_code_compiles(_code(conn))

    @pytest.mark.parametrize("gear_id,teeth,module,width,pa,bore,helix", GEAR_CASES)
    def test_involute_formula_present(self, gear_id, teeth, module, width, pa, bore, helix):
        conn = _ok_conn()
        if helix > 0:
            create_helical_gear_operation(
                conn, True, "Doc", gear_id, teeth, module, width,
                helix_angle=helix, pressure_angle=pa,
            )
        else:
            create_involute_gear_operation(
                conn, True, "Doc", gear_id, teeth, module, width,
                pressure_angle=pa,
            )
        code = _code(conn)
        assert_code_contains(code, "_ix", "_iy", "_polar")

    @pytest.mark.parametrize("gear_id,teeth,module,width,pa,bore,helix", GEAR_CASES)
    def test_tooth_count_in_code(self, gear_id, teeth, module, width, pa, bore, helix):
        conn = _ok_conn()
        if helix > 0:
            create_helical_gear_operation(
                conn, True, "Doc", gear_id, teeth, module, width,
                helix_angle=helix, pressure_angle=pa,
            )
        else:
            create_involute_gear_operation(
                conn, True, "Doc", gear_id, teeth, module, width,
                pressure_angle=pa,
            )
        assert_code_contains(_code(conn), str(teeth))


class TestEightGearGeometry:
    """Layer-C: Analytic geometry invariants for all 8 cases."""

    @pytest.mark.parametrize("gear_id,teeth,module,width,pa,bore,helix", GEAR_CASES)
    def test_pitch_diameter(self, gear_id, teeth, module, width, pa, bore, helix):
        d = _geom(teeth, module, pa)
        assert_pitch_diameter(teeth, module, d["pitch_dia"])

    @pytest.mark.parametrize("gear_id,teeth,module,width,pa,bore,helix", GEAR_CASES)
    def test_addendum_diameter(self, gear_id, teeth, module, width, pa, bore, helix):
        d = _geom(teeth, module, pa)
        assert_addendum_diameter(teeth, module, d["addendum_dia"])

    @pytest.mark.parametrize("gear_id,teeth,module,width,pa,bore,helix", GEAR_CASES)
    def test_base_smaller_than_pitch(self, gear_id, teeth, module, width, pa, bore, helix):
        d = _geom(teeth, module, pa)
        assert d["base_dia"] < d["pitch_dia"]

    @pytest.mark.parametrize("gear_id,teeth,module,width,pa,bore,helix", GEAR_CASES)
    def test_root_smaller_than_pitch(self, gear_id, teeth, module, width, pa, bore, helix):
        d = _geom(teeth, module, pa)
        assert d["root_dia"] < d["pitch_dia"]

    @pytest.mark.parametrize("gear_id,teeth,module,width,pa,bore,helix", GEAR_CASES)
    def test_addendum_larger_than_pitch(self, gear_id, teeth, module, width, pa, bore, helix):
        d = _geom(teeth, module, pa)
        assert d["addendum_dia"] > d["pitch_dia"]

    @pytest.mark.parametrize("gear_id,teeth,module,width,pa,bore,helix", GEAR_CASES)
    def test_involute_fn_positive(self, gear_id, teeth, module, width, pa, bore, helix):
        d = _geom(teeth, module, pa)
        assert d["involute_fn"] > 0.0

    @pytest.mark.parametrize("gear_id,teeth,module,width,pa,bore,helix", GEAR_CASES)
    def test_sampled_involute_on_curve(self, gear_id, teeth, module, width, pa, bore, helix):
        """50 sampled involute points must lie on the analytic involute (exact check)."""
        α = math.radians(pa)
        r_pitch = module * teeth / 2.0
        r_b = r_pitch * math.cos(α)
        r_outer = r_pitch + module
        t_tip = involute_parameter_at_radius(r_b, r_outer)
        pts = sample_involute(r_b, 0.0, t_tip, 50)
        # Direct exact check — invert the radius formula, no grid search.
        assert_on_involute_direct(pts, r_b)


class TestEightGearPairs:
    """Layer-D: Gear pair compatibility for standard 8-case matching sets."""

    def _pair(self, t1, m, t2):
        conn = MagicMock()
        resp = check_gear_pair_operation(conn, True, t1, m, t2, m)
        return json.loads(_text(resp))

    def test_10_20_mesh(self):
        d = self._pair(10, 1.0, 20)
        assert d["meshes"] is True

    def test_20_40_mesh(self):
        d = self._pair(20, 2.0, 40)
        assert d["meshes"] is True

    def test_ratio_2_to_1(self):
        d = self._pair(20, 2.0, 40)
        assert abs(d["gear_ratio"] - 2.0) < 1e-6

    def test_ratio_3_to_1(self):
        d = self._pair(10, 2.0, 30)
        assert abs(d["gear_ratio"] - 3.0) < 1e-6

    def test_standard_center_distance(self):
        d = self._pair(20, 2.0, 40)
        # r1 = 20, r2 = 40 → center = 60
        assert abs(d["theoretical_cd_mm"] - 60.0) < 1e-5

    def test_module_mismatch_does_not_mesh(self):
        conn = MagicMock()
        resp = check_gear_pair_operation(conn, True, 20, 2.0, 20, 1.5)
        d = json.loads(_text(resp))
        assert d["meshes"] is False

    def test_helical_geometry_stored(self):
        d = _geom(20, 2.0, helix_angle=15.0)
        assert d["helix_angle"] == 15.0
