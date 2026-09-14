"""Adversarial wire cases for the ``boolean_difference`` contract."""

from __future__ import annotations

from itertools import product
from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.boolean_difference_contract import (
    FeatureName,
    make_boolean_difference_failure,
    make_boolean_difference_success,
    make_boolean_difference_uncertain,
    parse_boolean_difference_response,
)
from freecad_mcp.operations.parametric_ops.boolean_difference import boolean_difference_operation


def _success():
    return make_boolean_difference_success(FeatureName("Feature001"), "Main Feature")


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_boolean_difference_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


@pytest.mark.parametrize("version", [None, True, False, 1.0, "1", 0, 2])
def test_contract_version_must_be_the_exact_integer(version):
    assert parse_boolean_difference_response(dict(_success(), contract_version=version))["success"] is False


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
    result = parse_boolean_difference_response(dict(_success(), **change))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["retry_safe"] is False


@pytest.mark.parametrize(
    "raw",
    [
        _success(),
        make_boolean_difference_failure("BUSY", "Retry after recompute", native_status="Busy"),
        make_boolean_difference_failure("INVALID_ARGUMENT", "Invalid name", retry_safe=False),
        *[
            make_boolean_difference_uncertain(
                "STATE_UNKNOWN",
                "Reconcile before replay",
                committed=committed,
                diagnostics={"request_id": "request-1"},
            )
            for committed in (None, False, True)
        ],
        make_boolean_difference_uncertain(
            "BOOLEAN_DIFFERENCE_ROLLBACK_UNCERTAIN",
            "Rollback failed",
            committed=None,
            native_status="RollbackFailed",
            rollback_failed=True,
            rollback_succeeded=False,
        ),
    ],
)
def test_valid_variants_round_trip_without_changing_evidence(raw):
    assert parse_boolean_difference_response(raw) == raw
    assert parse_boolean_difference_response(parse_boolean_difference_response(raw)) == raw


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
    result = parse_boolean_difference_response(raw)
    assert result["success"] is (
        success is True and committed is True and outcome == "committed" and retry_safe is False
    )


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = boolean_difference_operation(
        SimpleNamespace(boolean_difference=lost_response), True, "Doc", shape1='Shape1', shape2='Shape2', result_name='Result'
    )
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "BOOLEAN_DIFFERENCE_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["committed"] is None
    assert data["retry_safe"] is False
