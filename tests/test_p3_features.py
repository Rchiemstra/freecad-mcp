"""
Tests for P3 3D feature operations.

Layer-A: Schema / error propagation for typed JSON-RPC routing.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from mcp.types import TextContent

from freecad_mcp.operations.p3_features import (
    boolean_difference_operation,
    boolean_intersection_operation,
    boolean_union_operation,
    chamfer_feature_operation,
    fillet_feature_operation,
    helical_sweep_feature_operation,
    loft_feature_operation,
    revolve_feature_operation,
    sweep_feature_operation,
)


def _typed_ok(op: str, feature: str):
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    getattr(conn, op).return_value = {
        "contract_version": 1,
        "success": True,
        "ok": True,
        "outcome": "committed",
        "committed": True,
        "retry_safe": False,
        "feature": feature,
        "label": feature,
    }
    return conn


def _typed_fail(op: str, error: str = "oops"):
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    getattr(conn, op).return_value = {
        "contract_version": 1,
        "success": False,
        "ok": False,
        "outcome": "rejected",
        "committed": False,
        "retry_safe": True,
        "error_code": "OPERATION_FAILED",
        "error": error,
    }
    return conn


def _text(response) -> str:
    content = response.content if hasattr(response, "content") else response
    return " ".join(item.text for item in content if isinstance(item, TextContent))


class TestRevolveFeature:
    def test_success(self):
        resp = revolve_feature_operation(_typed_ok("revolve_feature", "Rev1"), True, "Doc", "Sketch", "Rev1")
        assert _text(resp)

    def test_failure(self):
        resp = revolve_feature_operation(_typed_fail("revolve_feature"), True, "Doc", "Sketch", "Rev1")
        assert "oops" in _text(resp) or "Failed" in _text(resp)

    def test_routes_typed_rpc(self):
        conn = _typed_ok("revolve_feature", "Rev1")
        revolve_feature_operation(conn, True, "Doc", "Sketch", "Rev1", angle=180.0, axis="Z_Axis")
        conn.revolve_feature.assert_called_once()


class TestLoftFeature:
    def test_success(self):
        resp = loft_feature_operation(_typed_ok("loft_feature", "Loft1"), True, "Doc", ["S1", "S2"], "Loft1")
        assert _text(resp)

    def test_routes_typed_rpc(self):
        conn = _typed_ok("loft_feature", "Loft1")
        loft_feature_operation(conn, True, "Doc", ["S1", "S2"], "Loft1")
        conn.loft_feature.assert_called_once()


class TestSweepFeature:
    def test_success(self):
        resp = sweep_feature_operation(_typed_ok("sweep_feature", "Sweep1"), True, "Doc", "Profile", "Spine", "Sweep1")
        assert _text(resp)

    def test_routes_typed_rpc(self):
        conn = _typed_ok("sweep_feature", "Sweep1")
        sweep_feature_operation(conn, True, "Doc", "Profile", "Spine", "Sweep1")
        conn.sweep_feature.assert_called_once()


class TestHelicalSweepFeature:
    def test_success(self):
        resp = helical_sweep_feature_operation(
            _typed_ok("helical_sweep_feature", "Helix1"), True, "Doc", "Profile", "Helix1", 2.0, 10.0, 5.0
        )
        assert _text(resp)


class TestFilletFeature:
    def test_success(self):
        resp = fillet_feature_operation(
            _typed_ok("fillet_feature", "Fillet1"), True, "Doc", "Pad", "Fillet1", 1.0, ["Edge1", "Edge2"]
        )
        assert _text(resp)


class TestChamferFeature:
    def test_success(self):
        resp = chamfer_feature_operation(
            _typed_ok("chamfer_feature", "Chamfer1"), True, "Doc", "Pad", "Chamfer1", 1.0, ["Edge1"]
        )
        assert _text(resp)


class TestBooleanUnion:
    def test_success(self):
        resp = boolean_union_operation(_typed_ok("boolean_union", "Union1"), True, "Doc", "Base1", "Tool1", "Union1")
        assert _text(resp)


class TestBooleanDifference:
    def test_success(self):
        resp = boolean_difference_operation(
            _typed_ok("boolean_difference", "Cut1"), True, "Doc", "Base1", "Tool1", "Cut1"
        )
        assert _text(resp)


class TestBooleanIntersection:
    def test_success(self):
        resp = boolean_intersection_operation(
            _typed_ok("boolean_intersection", "Common1"), True, "Doc", "Base1", "Tool1", "Common1"
        )
        assert _text(resp)
