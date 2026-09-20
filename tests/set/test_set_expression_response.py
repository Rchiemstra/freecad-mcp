"""Adversarial wire cases for the ``set_expression`` contract."""

from __future__ import annotations

import pytest

from freecad_mcp._shared.protocol.set_expression_contract import (
    make_set_expression_success,
    parse_set_expression_response,
)
from freecad_mcp.operations.parametric_ops.set_expression import (
    set_expression_operation,
)


def _success():
    return make_set_expression_success(object="Value", prop_path="Value", expression="Value")


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_set_expression_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


@pytest.mark.parametrize("version", [None, True, False, 1.0, "1", 0, 2])
def test_contract_version_must_be_the_exact_integer(version):
    assert parse_set_expression_response(dict(_success(), contract_version=version))["success"] is False


@pytest.mark.parametrize(
    "change",
    [
        {"rollback_failed": True},
        {"rollback_succeeded": True},
        {"native_status": "Rejected"},
        {"success": 1},
        {"ok": 1},
        {"committed": 1},
        {"retry_safe": 0},
        {"completion_uncertain": True},
    ],
)
def test_contradictory_or_malformed_success_cannot_escape(change):
    result = parse_set_expression_response(dict(_success(), **change))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_set_expression_response(raw) == raw


def test_transport_failure_preserves_unknown_model_state():
    class _Conn:
        def set_expression(self, *_args, **_kwargs):
            raise TimeoutError("response lost after request was sent")

    response = set_expression_operation(_Conn(), True, "Doc", "Value", "Value", "Value")
    assert response.isError is True
    envelope = response.structuredContent
    assert envelope["status"] == "unknown"
    data = envelope["data"]
    assert data["error_code"] == "SET_EXPRESSION_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False
    assert envelope["layers"]["transport_status"] != "succeeded"
