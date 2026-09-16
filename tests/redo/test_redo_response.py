"""Adversarial wire cases for the ``redo`` contract."""

from __future__ import annotations

from itertools import product
from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.redo_contract import (
    DocumentName,
    make_redo_failure,
    make_redo_success,
    make_redo_uncertain,
    parse_redo_response,
)
from freecad_mcp.operations.parametric_ops.redo import redo_operation


def _success():
    return make_redo_success(DocumentName("Doc"))


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_redo_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


@pytest.mark.parametrize("version", [None, True, False, 1.0, "1", 0, 2])
def test_contract_version_must_be_the_exact_integer(version):
    assert parse_redo_response(dict(_success(), contract_version=version))["success"] is False


@pytest.mark.parametrize(
    "change",
    [
        {"rollback_failed": True},
        {"rollback_succeeded": False},
        {"rollback_succeeded": True},
        {"native_status": "Rejected"},
        {"success": 1},
        {"ok": 1},
        {"committed": 1},
        {"retry_safe": 0},
        {'document_name': None},
    ],
)
def test_contradictory_or_malformed_success_cannot_escape(change):
    result = parse_redo_response(dict(_success(), **change))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_redo_response(raw) == raw


def test_valid_failure_round_trips():
    raw = make_redo_failure("BUSY", "Retry", native_status="Busy")
    assert parse_redo_response(raw) == raw


@pytest.mark.parametrize("committed", [None, False, True])
def test_valid_uncertain_round_trips(committed):
    raw = make_redo_uncertain("STATE_UNKNOWN", "Reconcile", committed=committed)
    assert parse_redo_response(raw) == raw


@pytest.mark.parametrize(
    ("success", "outcome", "retry_safe"),
    list(product((True, False), ("verified", "rejected", "uncertain", "compensated"), (True, False))),
)
def test_only_the_complete_success_discriminant_can_succeed(success, outcome, retry_safe):
    raw = dict(_success(), success=success, outcome=outcome, retry_safe=retry_safe)
    result = parse_redo_response(raw)
    assert result["success"] is (
        success is True and outcome == "verified" and retry_safe is False
    )


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    client = SimpleNamespace(
        redo=lost_response,
        get_active_screenshot=lambda: None,
    )
    response = redo_operation(client, "Doc")
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False
