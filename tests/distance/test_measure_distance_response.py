"""Adversarial wire cases for the measure_distance contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.measure_distance_contract import (
    make_measure_distance_failure,
    make_measure_distance_success,
    make_measure_distance_uncertain,
    parse_measure_distance_response,
)
from freecad_mcp.operations.parametric_ops.measure_distance import measure_distance_operation


def _success():
    return make_measure_distance_success(distance=0.0, unit="mm")


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_measure_distance_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_measure_distance_response(raw) == raw


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = measure_distance_operation(SimpleNamespace(measure_distance=lost_response), "Doc", "Box", "Box")
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "MEASURE_DISTANCE_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False


def test_contradictory_success_cannot_escape():
    result = parse_measure_distance_response(dict(_success(), rollback_failed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
