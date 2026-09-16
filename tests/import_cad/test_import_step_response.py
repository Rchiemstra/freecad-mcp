"""Adversarial wire cases for the import_step contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.import_step_contract import (
    make_import_step_failure,
    make_import_step_success,
    make_import_step_uncertain,
    parse_import_step_response,
)
from freecad_mcp.operations.parametric_ops.import_step import import_step_operation


def _success():
    return make_import_step_success(path="/tmp/out", imported=True)


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_import_step_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_import_step_response(raw) == raw


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = import_step_operation(SimpleNamespace(import_step=lost_response), "Doc", "/tmp/in.step")
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "IMPORT_STEP_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False


def test_contradictory_success_cannot_escape():
    result = parse_import_step_response(dict(_success(), rollback_failed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
