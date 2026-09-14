"""Adversarial wire cases for the common_volume_along_path contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.common_volume_along_path_contract import (
    make_common_volume_along_path_failure,
    make_common_volume_along_path_success,
    make_common_volume_along_path_uncertain,
    parse_common_volume_along_path_response,
)
from freecad_mcp.operations.parametric_ops.common_volume_along_path import common_volume_along_path_operation


def _success():
    return make_common_volume_along_path_success(moving_object="Mover", sample_count=1, volume_threshold_mm3=1e-6, max_common_volume_mm3=0.0, any_collision=False, samples=[])


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_common_volume_along_path_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_common_volume_along_path_response(raw) == raw


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = common_volume_along_path_operation(SimpleNamespace(common_volume_along_path=lost_response), "Doc", "Mover", ["Wall"], samples=[{"x": 0, "y": 0, "z": 0}])
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "COMMON_VOLUME_ALONG_PATH_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False


def test_contradictory_success_cannot_escape():
    result = parse_common_volume_along_path_response(dict(_success(), rollback_failed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
