"""Adversarial wire cases for the audit_hardcoded_dimensions contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.audit_hardcoded_dimensions_contract import (
    make_audit_hardcoded_dimensions_failure,
    make_audit_hardcoded_dimensions_success,
    make_audit_hardcoded_dimensions_uncertain,
    parse_audit_hardcoded_dimensions_response,
)
from freecad_mcp.operations.parametric_ops.audit_hardcoded_dimensions import audit_hardcoded_dimensions_operation


def _success():
    return make_audit_hardcoded_dimensions_success(clean=True, body="Body", count=0, findings=[])


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_audit_hardcoded_dimensions_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_audit_hardcoded_dimensions_response(raw) == raw


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = audit_hardcoded_dimensions_operation(SimpleNamespace(audit_hardcoded_dimensions=lost_response), "Doc", "Body", True)
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "AUDIT_HARDCODED_DIMENSIONS_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False


def test_contradictory_success_cannot_escape():
    result = parse_audit_hardcoded_dimensions_response(dict(_success(), rollback_failed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
