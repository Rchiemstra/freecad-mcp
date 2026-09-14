"""Adversarial wire cases for the ``move_object`` contract."""

from __future__ import annotations

from itertools import product
from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.move_object_contract import (
    make_move_object_failure,
    make_move_object_success,
    make_move_object_uncertain,
    parse_move_object_response,
)
from freecad_mcp.operations.parametric_ops.move_object import move_object_operation


def _success():
    return make_move_object_success(object_name="Value", target_container="Value")


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_move_object_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


@pytest.mark.parametrize("version", [None, True, False, 1.0, "1", 0, 2])
def test_contract_version_must_be_the_exact_integer(version):
    assert parse_move_object_response(dict(_success(), contract_version=version))["success"] is False


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
    result = parse_move_object_response(dict(_success(), **change))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_move_object_response(raw) == raw


def test_transport_failure_preserves_unknown_model_state():
    class _Conn:
        def _invoke_mutation_v2(self, *args, **kwargs):
            raise TimeoutError("response lost after request was sent")

    response = move_object_operation(_Conn(), True, "Doc", "Value", "Value", True)
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "MOVE_OBJECT_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False
