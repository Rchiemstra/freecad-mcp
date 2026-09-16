"""Adversarial wire cases for the validate_geometry contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.validate_geometry_contract import (
    make_validate_geometry_failure,
    make_validate_geometry_success,
    make_validate_geometry_uncertain,
    parse_validate_geometry_response,
)
from freecad_mcp.operations.parametric_ops.validate_geometry import validate_geometry_operation


def _success():
    return make_validate_geometry_success(object="Box", is_null=False, is_valid=True, is_closed=True, volume_mm3=1000.0, area_mm2=100.0, face_count=6, edge_count=12, vertex_count=8, shape_type="Solid", check_ok=True, check_errors=[])


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_validate_geometry_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_validate_geometry_response(raw) == raw


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = validate_geometry_operation(SimpleNamespace(validate_geometry=lost_response), "Doc", "Box")
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "VALIDATE_GEOMETRY_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False


def test_contradictory_success_cannot_escape():
    result = parse_validate_geometry_response(dict(_success(), rollback_failed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
