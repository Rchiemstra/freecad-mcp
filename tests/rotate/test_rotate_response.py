"""Adversarial wire cases for the rotate contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.rotate_contract import (
    make_rotate_failure,
    make_rotate_success,
    make_rotate_uncertain,
    parse_rotate_response,
)
from freecad_mcp.operations.parametric_ops.rotate import rotate_operation


def _success():
    return make_rotate_success(object="Box", label="Box")


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_rotate_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_rotate_response(raw) == raw


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = rotate_operation(SimpleNamespace(rotate=lost_response), True, "Doc", "Box", 0.0, 0.0, 1.0, 90.0)
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "ROTATE_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False


def test_contradictory_success_cannot_escape():
    result = parse_rotate_response(dict(_success(), rollback_failed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
