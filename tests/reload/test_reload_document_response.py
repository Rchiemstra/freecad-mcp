"""Adversarial wire cases for the ``reload_document`` contract."""

from __future__ import annotations

from itertools import product
from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.reload_document_contract import (
    DocumentName,
    make_reload_document_failure,
    make_reload_document_success,
    make_reload_document_uncertain,
    parse_reload_document_response,
)
from freecad_mcp.operations.parametric_ops.reload_document import reload_document_operation


def _success():
    return make_reload_document_success(DocumentName("Doc"))


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_reload_document_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


@pytest.mark.parametrize("version", [None, True, False, 1.0, "1", 0, 2])
def test_contract_version_must_be_the_exact_integer(version):
    assert parse_reload_document_response(dict(_success(), contract_version=version))["success"] is False


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
    result = parse_reload_document_response(dict(_success(), **change))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_reload_document_response(raw) == raw


def test_valid_failure_round_trips():
    raw = make_reload_document_failure("BUSY", "Retry", native_status="Busy")
    assert parse_reload_document_response(raw) == raw


@pytest.mark.parametrize("committed", [None, False, True])
def test_valid_uncertain_round_trips(committed):
    raw = make_reload_document_uncertain("STATE_UNKNOWN", "Reconcile", committed=committed)
    assert parse_reload_document_response(raw) == raw


@pytest.mark.parametrize(
    ("success", "committed", "outcome", "retry_safe"),
    list(product((True, False), (True, False, None), ("committed", "rejected", "uncertain"), (True, False))),
)
def test_only_the_complete_success_discriminant_can_succeed(success, committed, outcome, retry_safe):
    raw = dict(_success(), success=success, committed=committed, outcome=outcome, retry_safe=retry_safe)
    result = parse_reload_document_response(raw)
    assert result["success"] is (
        success is True and committed is True and outcome == "committed" and retry_safe is False
    )


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    client = SimpleNamespace(
        reload_document=lost_response,
        get_active_screenshot=lambda: None,
    )
    response = reload_document_operation(client, "Doc")
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False
