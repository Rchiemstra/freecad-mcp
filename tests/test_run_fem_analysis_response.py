"""Adversarial wire cases for the ``run_fem_analysis`` contract."""

from __future__ import annotations

from itertools import product
from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.run_fem_analysis_contract import (
    make_run_fem_analysis_failure,
    make_run_fem_analysis_success,
    make_run_fem_analysis_uncertain,
    parse_run_fem_analysis_response,
)
from freecad_mcp.operations.parametric_ops.run_fem_analysis import run_fem_analysis_operation


def _success():
    return make_run_fem_analysis_success(analysis_name="Value")


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_run_fem_analysis_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


@pytest.mark.parametrize("version", [None, True, False, 1.0, "1", 0, 2])
def test_contract_version_must_be_the_exact_integer(version):
    assert parse_run_fem_analysis_response(dict(_success(), contract_version=version))["success"] is False


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
    result = parse_run_fem_analysis_response(dict(_success(), **change))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_run_fem_analysis_response(raw) == raw


def test_transport_failure_preserves_unknown_model_state():
    class _Conn:
        def _invoke_mutation_v2(self, *args, **kwargs):
            raise TimeoutError("response lost after request was sent")

    response = run_fem_analysis_operation(_Conn(), True, "Doc", "Value", 600)
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "RUN_FEM_ANALYSIS_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False
