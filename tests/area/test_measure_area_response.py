"""Adversarial wire cases for the measure_area contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.measure_area_contract import (
    make_measure_area_failure,
    make_measure_area_success,
    make_measure_area_uncertain,
    parse_measure_area_response,
)
from freecad_mcp.operations.parametric_ops.measure_area import measure_area_operation


def _success():
    return make_measure_area_success(object="Box", area_mm2=100.0, area_cm2=1.0, unit="mm2", frame="global")


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_measure_area_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_measure_area_response(raw) == raw


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = measure_area_operation(SimpleNamespace(measure_area=lost_response), "Doc", "Box")
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "MEASURE_AREA_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False


def test_contradictory_success_cannot_escape():
    result = parse_measure_area_response(dict(_success(), rollback_failed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
