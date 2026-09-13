"""Adversarial wire cases for the ``linear_pattern_feature`` contract."""

from __future__ import annotations

from itertools import product
from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.linear_pattern_feature_contract import (
    FeatureName,
    make_linear_pattern_feature_failure,
    make_linear_pattern_feature_success,
    make_linear_pattern_feature_uncertain,
    parse_linear_pattern_feature_response,
)
from freecad_mcp.operations.parametric_ops.linear_pattern_feature import linear_pattern_feature_operation


def _success():
    return make_linear_pattern_feature_success(FeatureName("Feature001"), "Main Feature")


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_linear_pattern_feature_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


@pytest.mark.parametrize("version", [None, True, False, 1.0, "1", 0, 2])
def test_contract_version_must_be_the_exact_integer(version):
    assert parse_linear_pattern_feature_response(dict(_success(), contract_version=version))["success"] is False


@pytest.mark.parametrize(
    "change",
    [
        {"rollback_failed": True},
        {"rollback_succeeded": False},
        {"rollback_succeeded": True},
        {"native_status": "Rejected"},
        {"native_status": "RollbackFailed"},
        {"native_status": None},
        {"success": 1},
        {"ok": 1},
        {"committed": 1},
        {"retry_safe": 0},
        {"rollback_failed": "false"},
        {"native_status": []},
        {"error": ""},
        {"error_code": False},
        {"completion_uncertain": True},
        {"feature": " "},
        {"label": None},
        {"diagnostics": []},
    ],
)
def test_contradictory_or_malformed_success_cannot_escape(change):
    result = parse_linear_pattern_feature_response(dict(_success(), **change))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["retry_safe"] is False


@pytest.mark.parametrize(
    "raw",
    [
        _success(),
        make_linear_pattern_feature_failure("BUSY", "Retry after recompute", native_status="Busy"),
        make_linear_pattern_feature_failure("INVALID_ARGUMENT", "Invalid name", retry_safe=False),
        *[
            make_linear_pattern_feature_uncertain(
                "STATE_UNKNOWN",
                "Reconcile before replay",
                committed=committed,
                diagnostics={"request_id": "request-1"},
            )
            for committed in (None, False, True)
        ],
        make_linear_pattern_feature_uncertain(
            "LINEAR_PATTERN_FEATURE_ROLLBACK_UNCERTAIN",
            "Rollback failed",
            committed=None,
            native_status="RollbackFailed",
            rollback_failed=True,
            rollback_succeeded=False,
        ),
    ],
)
def test_valid_variants_round_trip_without_changing_evidence(raw):
    assert parse_linear_pattern_feature_response(raw) == raw
    assert parse_linear_pattern_feature_response(parse_linear_pattern_feature_response(raw)) == raw


@pytest.mark.parametrize(
    ("success", "committed", "outcome", "retry_safe"),
    list(
        product(
            (True, False),
            (True, False, None),
            ("committed", "rejected", "uncertain"),
            (True, False),
        )
    ),
)
def test_only_the_complete_success_discriminant_can_succeed(
    success, committed, outcome, retry_safe
):
    raw = dict(
        _success(), success=success, committed=committed, outcome=outcome, retry_safe=retry_safe
    )
    result = parse_linear_pattern_feature_response(raw)
    assert result["success"] is (
        success is True and committed is True and outcome == "committed" and retry_safe is False
    )


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = linear_pattern_feature_operation(
        SimpleNamespace(linear_pattern_feature=lost_response), True, "Doc", feature_name='Pad', pattern_name='Array', length=40.0, occurrences=5, direction='X_Axis', body_name=None, reversed_dir=False
    )
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "LINEAR_PATTERN_FEATURE_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["committed"] is None
    assert data["retry_safe"] is False
