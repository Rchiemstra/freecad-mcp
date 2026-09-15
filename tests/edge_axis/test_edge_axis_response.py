"""Adversarial wire cases for the edge_axis contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.edge_axis_contract import (
    make_edge_axis_failure,
    make_edge_axis_success,
    make_edge_axis_uncertain,
    parse_edge_axis_response,
)
from freecad_mcp.operations.parametric_ops.edge_axis import edge_axis_operation


def _success():
    return make_edge_axis_success(object="Box", subshape="Edge1", shape_type="line", global_center=[0.0,0.0,0.0], global_normal=[1.0,0.0,0.0])


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_edge_axis_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_edge_axis_response(raw) == raw


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = edge_axis_operation(SimpleNamespace(edge_axis=lost_response), "Doc", "Box", "Edge1")
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "EDGE_AXIS_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False


def test_contradictory_success_cannot_escape():
    result = parse_edge_axis_response(dict(_success(), rollback_failed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
