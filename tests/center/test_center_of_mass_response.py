"""Adversarial wire cases for the center_of_mass contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.center_of_mass_contract import (
    make_center_of_mass_failure,
    make_center_of_mass_success,
    make_center_of_mass_uncertain,
    parse_center_of_mass_response,
)
from freecad_mcp.operations.parametric_ops.center_of_mass import center_of_mass_operation


def _success():
    return make_center_of_mass_success(object="Box", x=0.5, y=0.5, z=0.5, unit="mm", method="assembly.solve()", frame="world")


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_center_of_mass_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_center_of_mass_response(raw) == raw


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = center_of_mass_operation(SimpleNamespace(center_of_mass=lost_response), "Doc", "Box")
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "CENTER_OF_MASS_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False


def test_contradictory_success_cannot_escape():
    result = parse_center_of_mass_response(dict(_success(), rollback_failed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
