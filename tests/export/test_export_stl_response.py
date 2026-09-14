"""Adversarial wire cases for the export_stl contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.export_stl_contract import (
    make_export_stl_failure,
    make_export_stl_success,
    make_export_stl_uncertain,
    parse_export_stl_response,
)
from freecad_mcp.operations.parametric_ops.export_stl import export_stl_operation


def _success():
    return make_export_stl_success(path="/tmp/out", exported=1, faces=12)


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_export_stl_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_export_stl_response(raw) == raw


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = export_stl_operation(SimpleNamespace(export_stl=lost_response), "Doc", "/tmp/out.stl")
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "EXPORT_STL_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False


def test_contradictory_success_cannot_escape():
    result = parse_export_stl_response(dict(_success(), rollback_failed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
