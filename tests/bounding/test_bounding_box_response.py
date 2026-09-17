"""Adversarial wire cases for the bounding_box contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.bounding_box_contract import (
    make_bounding_box_failure,
    make_bounding_box_success,
    make_bounding_box_uncertain,
    parse_bounding_box_response,
)
from freecad_mcp.operations.parametric_ops.bounding_box import bounding_box_operation


def _success():
    return make_bounding_box_success(object="Box", xmin=0.0, ymin=0.0, zmin=0.0, xmax=1.0, ymax=1.0, zmax=1.0, dx=1.0, dy=1.0, dz=1.0, diagonal=1.732, frame="world", used_linked_object=False)


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_bounding_box_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_bounding_box_response(raw) == raw


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = bounding_box_operation(SimpleNamespace(bounding_box=lost_response), "Doc", "Box")
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "BOUNDING_BOX_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False


def test_contradictory_success_cannot_escape():
    result = parse_bounding_box_response(dict(_success(), rollback_failed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
