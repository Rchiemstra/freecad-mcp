"""Adversarial wire cases for the export_brep contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.export_brep_contract import (
    make_export_brep_failure,
    make_export_brep_success,
    make_export_brep_uncertain,
    parse_export_brep_response,
)
from freecad_mcp.operations.parametric_ops.export_brep import export_brep_operation


def _success():
    return make_export_brep_success(path="/tmp/out", exported=True, object="Box")


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_export_brep_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_export_brep_response(raw) == raw


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = export_brep_operation(SimpleNamespace(export_brep=lost_response), "Doc", "Box", "/tmp/out.brep")
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "EXPORT_BREP_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False


def test_contradictory_success_cannot_escape():
    result = parse_export_brep_response(dict(_success(), rollback_failed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
