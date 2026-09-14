"""Adversarial wire cases for the solve_assembly contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.solve_assembly_contract import (
    make_solve_assembly_failure,
    make_solve_assembly_success,
    make_solve_assembly_uncertain,
    parse_solve_assembly_response,
)
from freecad_mcp.operations.parametric_ops.solve_assembly import solve_assembly_operation


def _success():
    return make_solve_assembly_success(assembly="Assembly", method="assembly.solve()", status="ok")


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_solve_assembly_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_solve_assembly_response(raw) == raw


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = solve_assembly_operation(SimpleNamespace(solve_assembly=lost_response), True, "Doc", "Assembly")
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "SOLVE_ASSEMBLY_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False


def test_contradictory_success_cannot_escape():
    result = parse_solve_assembly_response(dict(_success(), rollback_failed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
