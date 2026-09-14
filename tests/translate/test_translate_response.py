"""Adversarial wire cases for the translate contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.translate_contract import (
    make_translate_failure,
    make_translate_success,
    make_translate_uncertain,
    parse_translate_response,
)
from freecad_mcp.operations.parametric_ops.translate import translate_operation


def _success():
    return make_translate_success(object="Box", label="Box")


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_translate_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_translate_response(raw) == raw


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = translate_operation(SimpleNamespace(translate=lost_response), True, "Doc", "Box", 1.0, 0.0, 0.0)
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "TRANSLATE_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False


def test_contradictory_success_cannot_escape():
    result = parse_translate_response(dict(_success(), rollback_failed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
