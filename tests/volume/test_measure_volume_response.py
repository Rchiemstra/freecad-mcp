"""Adversarial wire cases for the measure_volume contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.measure_volume_contract import (
    make_measure_volume_failure,
    make_measure_volume_success,
    make_measure_volume_uncertain,
    parse_measure_volume_response,
)
from freecad_mcp.operations.parametric_ops.measure_volume import measure_volume_operation


def _success():
    return make_measure_volume_success(object="Box", volume_mm3=1000.0, unit="mm3", frame="global", used_linked_object=False)


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_measure_volume_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_measure_volume_response(raw) == raw


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = measure_volume_operation(SimpleNamespace(measure_volume=lost_response), "Doc", "Box")
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "MEASURE_VOLUME_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False


def test_contradictory_success_cannot_escape():
    result = parse_measure_volume_response(dict(_success(), rollback_failed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
