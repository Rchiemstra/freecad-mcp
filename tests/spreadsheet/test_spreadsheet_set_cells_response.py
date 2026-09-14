"""Adversarial wire cases for the ``spreadsheet_set_cells`` contract."""

from __future__ import annotations

from itertools import product
from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.spreadsheet_set_cells_contract import (
    make_spreadsheet_set_cells_failure,
    make_spreadsheet_set_cells_success,
    make_spreadsheet_set_cells_uncertain,
    parse_spreadsheet_set_cells_response,
)
from freecad_mcp.operations.parametric_ops.spreadsheet_set_cells import spreadsheet_set_cells_operation


def _success():
    return make_spreadsheet_set_cells_success(sheet="Value")


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_spreadsheet_set_cells_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


@pytest.mark.parametrize("version", [None, True, False, 1.0, "1", 0, 2])
def test_contract_version_must_be_the_exact_integer(version):
    assert parse_spreadsheet_set_cells_response(dict(_success(), contract_version=version))["success"] is False


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
    result = parse_spreadsheet_set_cells_response(dict(_success(), **change))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_spreadsheet_set_cells_response(raw) == raw


def test_transport_failure_preserves_unknown_model_state():
    class _Conn:
        def _invoke_mutation_v2(self, *args, **kwargs):
            raise TimeoutError("response lost after request was sent")

    response = spreadsheet_set_cells_operation(_Conn(), True, "Doc", "Value", [{"address": "A1", "value": 1}])
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "SPREADSHEET_SET_CELLS_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False
