"""Adversarial wire cases for the sketch_edit_constraint contract."""

from __future__ import annotations

from itertools import product
from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.sketch_edit_constraint_contract import (
    SketchName,
    make_sketch_edit_constraint_failure,
    make_sketch_edit_constraint_success,
    make_sketch_edit_constraint_uncertain,
    parse_sketch_edit_constraint_response,
)
from freecad_mcp.operations.parametric_ops.sketch_edit_constraint import sketch_edit_constraint_operation


def _success():
    return make_sketch_edit_constraint_success(SketchName("Sketch"), 0, "R")


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_sketch_edit_constraint_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


@pytest.mark.parametrize("version", [None, True, False, 1.0, "1", 0, 2])
def test_contract_version_must_be_the_exact_integer(version):
    assert (
        parse_sketch_edit_constraint_response(dict(_success(), contract_version=version))["success"] is False
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
        {"sketch": " "},
        {"diagnostics": []},
    ],
)
def test_contradictory_or_malformed_success_cannot_escape(change):
    result = parse_sketch_edit_constraint_response(dict(_success(), **change))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["retry_safe"] is False


@pytest.mark.parametrize(
    "raw",
    [
        _success(),
        make_sketch_edit_constraint_failure("BUSY", "Retry after recompute", native_status="Busy"),
        make_sketch_edit_constraint_failure("INVALID_ARGUMENT", "Invalid name", retry_safe=False),
        *[
            make_sketch_edit_constraint_uncertain(
                "STATE_UNKNOWN",
                "Reconcile before replay",
                committed=committed,
                diagnostics={"request_id": "request-1"},
            )
            for committed in (None, False, True)
        ],
        make_sketch_edit_constraint_uncertain(
            "SKETCH_EDIT_CONSTRAINT_ROLLBACK_UNCERTAIN",
            "Rollback failed",
            committed=None,
            native_status="RollbackFailed",
            rollback_failed=True,
            rollback_succeeded=False,
        ),
    ],
)
def test_valid_variants_round_trip_without_changing_evidence(raw):
    assert parse_sketch_edit_constraint_response(raw) == raw
    assert parse_sketch_edit_constraint_response(parse_sketch_edit_constraint_response(raw)) == raw


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
    result = parse_sketch_edit_constraint_response(raw)
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
        {"sketch": _success()["sketch"]},
        {"completion_uncertain": True},
    ],
)
def test_contradictory_failure_never_proves_rejection(change):
    result = parse_sketch_edit_constraint_response(
        dict(make_sketch_edit_constraint_failure("REJECTED", "Rejected"), **change)
    )
    assert result["outcome"] == "uncertain"
    assert result["retry_safe"] is False


def test_gui_completion_timeout_preserves_unknown_model_state():
    raw = {
        "success": False,
        "error_code": "GUI_COMPLETION_UNCERTAIN",
        "error": "Timed out",
        "completion_uncertain": True,
    }
    response = sketch_edit_constraint_operation(
        SimpleNamespace(sketch_edit_constraint=lambda *_args, **_kwargs: raw), True, "Doc", "Sketch", 7.0, "R", None
    )
    assert response.isError is True
    assert response.structuredContent["data"]["outcome"] == "uncertain"
    assert response.structuredContent["data"]["committed"] is None


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = sketch_edit_constraint_operation(
        SimpleNamespace(sketch_edit_constraint=lost_response), True, "Doc", "Sketch", 7.0, "R", None
    )
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "SKETCH_EDIT_CONSTRAINT_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["committed"] is None
    assert data["retry_safe"] is False
