"""Adversarial wire cases for the create_helical_gear contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.create_helical_gear_contract import (
    make_create_helical_gear_failure,
    make_create_helical_gear_success,
    make_create_helical_gear_uncertain,
    parse_create_helical_gear_response,
)
from freecad_mcp.operations.parametric_ops.create_helical_gear import create_helical_gear_operation


def _success():
    return make_create_helical_gear_success(body="Gear_Body", sketch="Gear_Sketch", feature="Gear", teeth=8, module=2.0)


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_create_helical_gear_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_create_helical_gear_response(raw) == raw


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = create_helical_gear_operation(SimpleNamespace(create_helical_gear=lost_response), True, "Doc", "Gear", 8, 2.0, 10.0)
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "CREATE_HELICAL_GEAR_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False


def test_contradictory_success_cannot_escape():
    result = parse_create_helical_gear_response(dict(_success(), rollback_failed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
