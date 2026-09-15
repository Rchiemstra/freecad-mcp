"""Adversarial wire cases for the match_subshape contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.match_subshape_contract import (
    make_match_subshape_failure,
    make_match_subshape_success,
    make_match_subshape_uncertain,
    parse_match_subshape_response,
)
from freecad_mcp.operations.parametric_ops.match_subshape import match_subshape_operation


def _success():
    return make_match_subshape_success(source="Box", target="Box", matches=[])


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_match_subshape_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_match_subshape_response(raw) == raw


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = match_subshape_operation(SimpleNamespace(match_subshape=lost_response), "Doc", "Box", "Face1", "Cylinder", 10, 1.0)
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "MATCH_SUBSHAPE_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False


def test_contradictory_success_cannot_escape():
    result = parse_match_subshape_response(dict(_success(), rollback_failed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
