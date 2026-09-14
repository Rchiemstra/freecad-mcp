"""Adversarial wire cases for the create_assembly_joint contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.create_assembly_joint_contract import (
    make_create_assembly_joint_failure,
    make_create_assembly_joint_success,
    make_create_assembly_joint_uncertain,
    parse_create_assembly_joint_response,
)
from freecad_mcp.operations.parametric_ops.create_assembly_joint import create_assembly_joint_operation


def _success():
    return make_create_assembly_joint_success(joint="Joint", label="Assembly", joint_type="Fixed", assembly="Assembly")


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_create_assembly_joint_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_create_assembly_joint_response(raw) == raw


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = create_assembly_joint_operation(SimpleNamespace(create_assembly_joint=lost_response), True, "Doc", "Assembly", "Fixed", "A", "B")
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "CREATE_ASSEMBLY_JOINT_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False


def test_contradictory_success_cannot_escape():
    result = parse_create_assembly_joint_response(dict(_success(), rollback_failed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
