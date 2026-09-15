"""Adversarial wire cases for the set_color contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.set_color_contract import (
    make_set_color_failure,
    make_set_color_success,
    make_set_color_uncertain,
    parse_set_color_response,
)
from freecad_mcp.operations.parametric_ops.set_color import set_color_operation


def _success():
    return make_set_color_success(object="Box", r=1.0, g=0.0, b=0.0, transparency=0.0)


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_set_color_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_set_color_response(raw) == raw


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = set_color_operation(SimpleNamespace(set_color=lost_response), True, "Doc", "Box", 1.0, 0.0, 0.0, 0.0)
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "SET_COLOR_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False


def test_contradictory_success_cannot_escape():
    result = parse_set_color_response(dict(_success(), rollback_failed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
