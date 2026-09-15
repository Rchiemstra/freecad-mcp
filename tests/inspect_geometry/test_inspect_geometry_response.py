"""Adversarial wire cases for the inspect_geometry contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.inspect_geometry_contract import (
    make_inspect_geometry_failure,
    make_inspect_geometry_success,
    make_inspect_geometry_uncertain,
    parse_inspect_geometry_response,
)
from freecad_mcp.operations.parametric_ops.inspect_geometry import inspect_geometry_operation


def _success():
    return make_inspect_geometry_success(object="Box", type_id="Part::Feature", placement={}, global_placement={}, parent_chain=[], local_bbox={}, global_bbox={})


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_inspect_geometry_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_inspect_geometry_response(raw) == raw


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = inspect_geometry_operation(SimpleNamespace(inspect_geometry=lost_response), "Doc", "Box", None)
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "INSPECT_GEOMETRY_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False


def test_contradictory_success_cannot_escape():
    result = parse_inspect_geometry_response(dict(_success(), rollback_failed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
