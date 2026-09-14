"""Adversarial wire cases for the ``sketch_extend`` contract."""

from __future__ import annotations

from itertools import product
from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.sketch_extend_contract import (
    SketchName,
    make_sketch_extend_failure,
    make_sketch_extend_success,
    make_sketch_extend_uncertain,
    parse_sketch_extend_response,
)
from freecad_mcp.operations.parametric_ops.sketch_extend import sketch_extend_operation


def _success():
    return make_sketch_extend_success(SketchName("Sketch"))


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_sketch_extend_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


@pytest.mark.parametrize("version", [None, True, False, 1.0, "1", 0, 2])
def test_contract_version_must_be_the_exact_integer(version):
    assert parse_sketch_extend_response(dict(_success(), contract_version=version))["success"] is False


@pytest.mark.parametrize(
    "change",
    [
        {"rollback_failed": True},
        {"rollback_succeeded": False},
        {"native_status": "Rejected"},
        {"success": 1},
        {"ok": 1},
        {"committed": 1},
        {"retry_safe": 0},
        {"completion_uncertain": True},
        {"sketch": " "},
        {"sketch": " "},
        {"diagnostics": []},
    ],
)
def test_contradictory_or_malformed_success_cannot_escape(change):
    result = parse_sketch_extend_response(dict(_success(), **change))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["retry_safe"] is False


@pytest.mark.parametrize(
    "raw",
    [
        _success(),
        make_sketch_extend_failure("BUSY", "Retry after recompute", native_status="Busy"),
        make_sketch_extend_failure("INVALID_ARGUMENT", "Invalid name", retry_safe=False),
        *[
            make_sketch_extend_uncertain("STATE_UNKNOWN", "Reconcile before replay", committed=committed)
            for committed in (None, False, True)
        ],
    ],
)
def test_valid_variants_round_trip_without_changing_evidence(raw):
    assert parse_sketch_extend_response(raw) == raw
    assert parse_sketch_extend_response(parse_sketch_extend_response(raw)) == raw


@pytest.mark.parametrize(
    ("success", "committed", "outcome", "retry_safe"),
    list(product((True, False), (True, False, None), ("committed", "rejected", "uncertain"), (True, False))),
)
def test_only_the_complete_success_discriminant_can_succeed(success, committed, outcome, retry_safe):
    raw = dict(_success(), success=success, committed=committed, outcome=outcome, retry_safe=retry_safe)
    result = parse_sketch_extend_response(raw)
    assert result["success"] is (
        success is True and committed is True and outcome == "committed" and retry_safe is False
    )


def test_gui_completion_timeout_preserves_unknown_model_state():
    raw = {
        "success": False,
        "error_code": "GUI_COMPLETION_UNCERTAIN",
        "error": "Timed out",
        "completion_uncertain": True,
    }
    response = sketch_extend_operation(
        SimpleNamespace(sketch_extend=lambda *_args, **_kwargs: raw), True, "Doc", "Sketch", 0, 2.0, 2
    )
    assert response.isError is True
    assert response.structuredContent["data"]["outcome"] == "uncertain"


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = sketch_extend_operation(
        SimpleNamespace(sketch_extend=lost_response), True, "Doc", "Sketch", 0, 2.0, 2
    )
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "SKETCH_EXTEND_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False
