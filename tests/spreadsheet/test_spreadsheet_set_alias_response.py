"""Adversarial wire cases for the ``spreadsheet_set_alias`` contract."""

from __future__ import annotations

from itertools import product
from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.spreadsheet_set_alias_contract import (
    make_spreadsheet_set_alias_failure,
    make_spreadsheet_set_alias_success,
    make_spreadsheet_set_alias_uncertain,
    parse_spreadsheet_set_alias_response,
)
from freecad_mcp.operations.parametric_ops.spreadsheet_set_alias import spreadsheet_set_alias_operation


def _success():
    return make_spreadsheet_set_alias_success(sheet="Value", address="Value", alias="Value")


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_spreadsheet_set_alias_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


@pytest.mark.parametrize("version", [None, True, False, 1.0, "1", 0, 2])
def test_contract_version_must_be_the_exact_integer(version):
    assert parse_spreadsheet_set_alias_response(dict(_success(), contract_version=version))["success"] is False


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
    result = parse_spreadsheet_set_alias_response(dict(_success(), **change))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_spreadsheet_set_alias_response(raw) == raw


def test_transport_failure_preserves_unknown_model_state():
    class _Conn:
        def _invoke_mutation_v2(self, *args, **kwargs):
            raise TimeoutError("response lost after request was sent")

    response = spreadsheet_set_alias_operation(_Conn(), True, "Doc", "Value", "Value", "Value")
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "SPREADSHEET_SET_ALIAS_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False
