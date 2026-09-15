"""Adversarial wire cases for the face_normal contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.face_normal_contract import (
    make_face_normal_failure,
    make_face_normal_success,
    make_face_normal_uncertain,
    parse_face_normal_response,
)
from freecad_mcp.operations.parametric_ops.face_normal import face_normal_operation


def _success():
    return make_face_normal_success(object="Box", subshape="Face1", shape_type="face", global_center=[0.0,0.0,0.0], global_normal=[0.0,0.0,1.0])


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_face_normal_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_face_normal_response(raw) == raw


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = face_normal_operation(SimpleNamespace(face_normal=lost_response), "Doc", "Box", "Face1")
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "FACE_NORMAL_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False


def test_contradictory_success_cannot_escape():
    result = parse_face_normal_response(dict(_success(), rollback_failed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
