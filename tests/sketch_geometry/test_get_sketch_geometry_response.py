"""Adversarial wire cases for the get_sketch_geometry contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.get_sketch_geometry_contract import (
    make_get_sketch_geometry_failure,
    make_get_sketch_geometry_success,
    make_get_sketch_geometry_uncertain,
    parse_get_sketch_geometry_response,
)
from freecad_mcp.operations.parametric_ops.get_sketch_geometry import get_sketch_geometry_operation


def _success():
    return make_get_sketch_geometry_success(sketch_name="Sketch", geometry_count=0, geometry=[], constraints=[], external_geometry=[])


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_get_sketch_geometry_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_get_sketch_geometry_response(raw) == raw


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = get_sketch_geometry_operation(SimpleNamespace(get_sketch_geometry=lost_response), "Doc", "Sketch")
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "GET_SKETCH_GEOMETRY_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False


def test_contradictory_success_cannot_escape():
    result = parse_get_sketch_geometry_response(dict(_success(), rollback_failed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
