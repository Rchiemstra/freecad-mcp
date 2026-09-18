"""Adversarial wire cases for the pocket_feature contract."""

from __future__ import annotations

from itertools import product
from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.pocket_feature_contract import (
    PocketName,
    make_pocket_feature_failure,
    make_pocket_feature_success,
    make_pocket_feature_uncertain,
    parse_pocket_feature_response,
)
from freecad_mcp.operations.parametric_ops.pocket_feature import (
    pocket_feature_operation,
)


def _success():
    return make_pocket_feature_success(PocketName("Pocket001"), "Main Pocket")


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_pocket_feature_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


@pytest.mark.parametrize("version", [None, True, False, 1.0, "1", 0, 2])
def test_contract_version_must_be_the_exact_integer(version):
    assert (
        parse_pocket_feature_response(dict(_success(), contract_version=version))["success"] is False
    )


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
        {"pocket": " "},
        {"diagnostics": []},
    ],
)
def test_contradictory_or_malformed_success_cannot_escape(change):
    result = parse_pocket_feature_response(dict(_success(), **change))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["retry_safe"] is False


@pytest.mark.parametrize(
    "raw",
    [
        _success(),
        make_pocket_feature_failure("BUSY", "Retry after recompute", native_status="Busy"),
        make_pocket_feature_failure("INVALID_ARGUMENT", "Invalid name", retry_safe=False),
        *[
            make_pocket_feature_uncertain(
                "STATE_UNKNOWN",
                "Reconcile before replay",
                committed=committed,
                diagnostics={"request_id": "request-1"},
            )
            for committed in (None, False, True)
        ],
        make_pocket_feature_uncertain(
            "POCKET_FEATURE_ROLLBACK_UNCERTAIN",
            "Rollback failed",
            committed=None,
            native_status="RollbackFailed",
            rollback_failed=True,
            rollback_succeeded=False,
        ),
    ],
)
def test_valid_variants_round_trip_without_changing_evidence(raw):
    assert parse_pocket_feature_response(raw) == raw
    assert parse_pocket_feature_response(parse_pocket_feature_response(raw)) == raw


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
    result = parse_pocket_feature_response(raw)
    assert result["success"] is (
        success is True and committed is True and outcome == "committed" and retry_safe is False
    )


@pytest.mark.parametrize(
    "change",
    [
        {"committed": True},
        {"rollback_failed": True},
        {"rollback_succeeded": False},
        {"native_status": "Committed"},
        {"native_status": "RollbackFailed"},
        {"retry_safe": 1},
        {"error": ""},
        {"pocket": _success()["pocket"]},
        {"completion_uncertain": True},
    ],
)
def test_contradictory_failure_never_proves_rejection(change):
    result = parse_pocket_feature_response(
        dict(make_pocket_feature_failure("REJECTED", "Rejected"), **change)
    )
    assert result["outcome"] == "uncertain"
    assert result["retry_safe"] is False


_REQUEST_ID = "11111111-2222-4333-8444-555555555555"


def test_gui_completion_timeout_preserves_unknown_model_state():
    raw = {
        "success": False,
        "error_code": "GUI_COMPLETION_UNCERTAIN",
        "error": "Timed out",
        "completion_uncertain": True,
    }
    response = pocket_feature_operation(
        SimpleNamespace(pocket_feature=lambda *_args, **_kwargs: raw), True, "Doc", "Sketch", "Pocket", 5.0
    )
    assert response.isError is True
    assert response.structuredContent["data"]["outcome"] == "uncertain"
    assert response.structuredContent["data"]["committed"] is None


def test_gui_timeout_during_execution_reports_timed_out_not_failed():
    raw = {
        "success": False,
        "request_id": _REQUEST_ID,
        "error_code": "GUI_TIMEOUT_DURING_EXECUTION",
        "timeout_stage": "during_execution",
        "error": "Timed out during execution",
        "completion_uncertain": True,
        "mutation_started": True,
    }
    response = pocket_feature_operation(
        SimpleNamespace(pocket_feature=lambda *_args, **_kwargs: raw),
        True,
        "Doc",
        "Sketch",
        "Pocket",
        5.0,
    )
    envelope = response.structuredContent
    assert envelope["status"] in {"timed_out", "unknown"}
    assert envelope["status"] != "failed"
    assert envelope["correlation"]["request_id"] == _REQUEST_ID
    assert envelope["data"]["error_code"] == "GUI_TIMEOUT_DURING_EXECUTION"


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = pocket_feature_operation(
        SimpleNamespace(pocket_feature=lost_response), True, "Doc", "Sketch", "Pocket", 5.0
    )
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "POCKET_FEATURE_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["committed"] is None
    assert data["retry_safe"] is False
