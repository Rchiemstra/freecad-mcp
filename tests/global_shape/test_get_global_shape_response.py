"""Adversarial wire cases for the get_global_shape contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.get_global_shape_contract import (
    make_get_global_shape_failure,
    make_get_global_shape_success,
    make_get_global_shape_uncertain,
    parse_get_global_shape_response,
)
from freecad_mcp.operations.parametric_ops.get_global_shape import get_global_shape_operation


def _success():
    return make_get_global_shape_success(object="Box", frame="global", volume_mm3=1000.0, area_mm2=100.0, center_of_mass=[0.0,0.0,0.0], bbox={}, solids=1, faces=6, edges=12)


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_get_global_shape_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_get_global_shape_response(raw) == raw


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = get_global_shape_operation(SimpleNamespace(get_global_shape=lost_response), "Doc", "Box")
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "GET_GLOBAL_SHAPE_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False


def test_contradictory_success_cannot_escape():
    result = parse_get_global_shape_response(dict(_success(), rollback_failed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
