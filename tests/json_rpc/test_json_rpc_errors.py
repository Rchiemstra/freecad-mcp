"""Focused contracts for JSON-RPC application error conversion."""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path

import pytest

from addon.FreeCADMCP.rpc_server.json_rpc_errors import json_rpc_error_from_result

pytestmark = pytest.mark.unit

_SEMANTIC_SNAPSHOT = (
    Path(__file__).resolve().parent / "fixtures/freecad_rpc_contract_snapshot.json"
)


@pytest.mark.parametrize(
    "result",
    [
        None,
        True,
        2**63 - 1,
        {"ok": True, "error": "diagnostic preserved"},
        {"success": True, "error_code": "DOCUMENT_CONFLICT"},
        {"error": "not an explicit failure"},
        {"status": "cancelled"},
    ],
)
def test_success_results_are_not_converted(result):
    assert json_rpc_error_from_result(result) is None


@pytest.mark.parametrize("failure_field", ["ok", "success"])
def test_generic_failure_uses_frozen_normalization(failure_field):
    result = {
        failure_field: False,
        "error": "operation failed",
        "details": {"request_id": "request-1", "shared": "details"},
        "shared": "outer",
        "document": "redacted-document",
    }
    original = deepcopy(result)

    error = json_rpc_error_from_result(result)

    assert error == {
        "code": -32000,
        "message": "operation failed",
        "data": {
            "request_id": "request-1",
            "shared": "details",
            "details": {"request_id": "request-1", "shared": "details"},
            "document": "redacted-document",
            "error_code": "LEGACY_FAILURE",
        },
    }
    assert result == original


@pytest.mark.parametrize(
    ("semantic_code", "json_rpc_code"),
    [
        ("DOCUMENT_CONFLICT", -32001),
        ("DOCUMENT_LEASE_CONFLICT", -32001),
        ("SAVE_AS_DESTINATION_CONFLICT", -32001),
        ("document_locked_by_other", -32001),
        ("LEASE_GENERATION_MISMATCH", -32001),
        ("LEASE_STALE", -32002),
        ("stale_lock_recovery_required", -32002),
        ("LOCKED_ERROR_HANDOFF_CANCELLED", -32003),
        ("REQUEST_CANCELLED_AFTER_MUTATION", -32003),
        ("WORKER_CANCELLED", -32003),
        ("DOCUMENT_LIFECYCLE_REJECTED", -32004),
        ("LEASE_STATE_FORBIDS_OPERATION", -32004),
        ("invalid_lease_state", -32004),
        ("DOCUMENT_CLOSE_REJECTED", -32004),
    ],
)
def test_semantic_failure_categories_have_stable_application_codes(
    semantic_code, json_rpc_code
):
    result = {
        "success": False,
        "error_code": semantic_code,
        "message": "semantic failure",
        "request_id": "request-2",
    }

    assert json_rpc_error_from_result(result) == {
        "code": json_rpc_code,
        "message": "semantic failure",
        "data": {
            "request_id": "request-2",
            "error_code": semantic_code,
        },
    }


def test_code_and_message_field_precedence_is_deterministic():
    error = json_rpc_error_from_result(
        {
            "ok": False,
            "code": "DOCUMENT_CONFLICT",
            "error_code": "LEASE_STALE",
            "message": "preferred message",
            "error": "fallback message",
            "details": {"changed_semantic_keys": ["model"]},
            "expected_revisions": {"model": 3},
            "current_revisions": {"model": 4},
        }
    )

    assert error == {
        "code": -32001,
        "message": "preferred message",
        "data": {
            "changed_semantic_keys": ["model"],
            "details": {"changed_semantic_keys": ["model"]},
            "expected_revisions": {"model": 3},
            "current_revisions": {"model": 4},
            "error_code": "DOCUMENT_CONFLICT",
        },
    }


def test_false_indicator_requires_the_boolean_singleton():
    assert json_rpc_error_from_result({"success": 0, "error": "not boolean"}) is None
    assert json_rpc_error_from_result({"ok": None, "error": "not boolean"}) is None


def test_default_message_and_code_are_stable():
    assert json_rpc_error_from_result({"success": False}) == {
        "code": -32000,
        "message": "RPC failed",
        "data": {"error_code": "LEGACY_FAILURE"},
    }


@pytest.mark.parametrize(
    ("semantic_code", "details", "json_rpc_code"),
    [
        ("LEASE_PROTOCOL_UNAVAILABLE", {}, -32000),
        ("REQUEST_ID_REUSE", {}, -32001),
        ("REQUEST_IN_PROGRESS", {}, -32001),
        ("REQUEST_CANCELLED_AFTER_MUTATION", {}, -32003),
        ("LEASE_STATE_FORBIDS_OPERATION", {"state": "STALE"}, -32002),
        ("DOCUMENT_LEASE_CONFLICT", {}, -32001),
        ("DOCUMENT_CLOSE_REJECTED", {}, -32004),
    ],
)
def test_nested_public_error_shapes_preserve_semantics(
    semantic_code, details, json_rpc_code
):
    result = {
        "ok": False,
        "request_id": "request-3",
        "addon_runtime_id": "runtime-3",
        "error": {
            "code": semantic_code,
            "message": "Public protocol rejection",
            "details": details,
        },
    }

    assert json_rpc_error_from_result(result) == {
        "code": json_rpc_code,
        "message": "Public protocol rejection",
        "data": {
            **details,
            "request_id": "request-3",
            "addon_runtime_id": "runtime-3",
            "error_code": semantic_code,
        },
    }


def test_error_data_is_recursively_redacted_and_independent():
    result = {
        "success": False,
        "error_code": "DOCUMENT_CONFLICT",
        "details": {
            "token": "top-secret-token",
            "nested": [{"session_token": "session-secret", "value": [1]}],
        },
        "lease_secret": "outer-secret",
    }

    converted = json_rpc_error_from_result(result)

    assert converted == {
        "code": -32001,
        "message": "RPC failed",
        "data": {
            "token": "<redacted>",
            "nested": [{"session_token": "<redacted>", "value": [1]}],
            "details": {
                "token": "<redacted>",
                "nested": [{"session_token": "<redacted>", "value": [1]}],
            },
            "lease_secret": "<redacted>",
            "error_code": "DOCUMENT_CONFLICT",
        },
    }
    converted["data"]["nested"][0]["value"].append(2)
    assert result["details"]["nested"][0]["value"] == [1]


def test_nested_public_error_extensions_are_preserved_and_redacted():
    result = {
        "ok": False,
        "error": {
            "code": "ACQUISITION_RESULT_NOT_REPLAYABLE",
            "message": "Acquisition result requires a claim",
            "claimable": True,
            "claim_token": "claim-secret",
        },
    }

    assert json_rpc_error_from_result(result) == {
        "code": -32000,
        "message": "Acquisition result requires a claim",
        "data": {
            "claimable": True,
            "claim_token": "<redacted>",
            "error_code": "ACQUISITION_RESULT_NOT_REPLAYABLE",
        },
    }


@pytest.mark.parametrize(
    ("semantic_code", "json_rpc_code"),
    [
        ("REQUEST_NOT_CANCELLABLE", -32004),
        ("lock_not_stale", -32000),
    ],
)
def test_negated_codes_are_not_misclassified(semantic_code, json_rpc_code):
    converted = json_rpc_error_from_result(
        {"ok": False, "error_code": semantic_code}
    )

    assert converted["code"] == json_rpc_code


def test_stale_state_context_overrides_general_lifecycle_category():
    converted = json_rpc_error_from_result(
        {
            "ok": False,
            "error_code": "LEASE_STATE_FORBIDS_OPERATION",
            "details": {"state": "STALE"},
        }
    )

    assert converted == {
        "code": -32002,
        "message": "RPC failed",
        "data": {
            "state": "STALE",
            "details": {"state": "STALE"},
            "error_code": "LEASE_STATE_FORBIDS_OPERATION",
        },
    }


def test_top_level_stale_state_is_accepted_for_legacy_compatibility():
    converted = json_rpc_error_from_result(
        {
            "ok": False,
            "error_code": "LEASE_STATE_FORBIDS_OPERATION",
            "state": "STALE",
        }
    )

    assert converted["code"] == -32002
    assert converted["data"]["state"] == "STALE"


def test_every_frozen_result_example_obeys_the_declared_failure_indicators():
    snapshot = json.loads(_SEMANTIC_SNAPSHOT.read_text(encoding="utf-8"))
    indicators = snapshot["legacy_error_normalization"]["failure_indicators"]
    converted = 0

    for contract in snapshot["methods"].values():
        for result in contract["result_examples"]:
            is_failure = isinstance(result, Mapping) and any(
                result.get(key) is value for key, value in indicators.items()
            )
            error = json_rpc_error_from_result(result)
            if is_failure:
                converted += 1
                assert error is not None
                assert isinstance(error["code"], int)
                assert error["data"]["error_code"] == (
                    result.get("code")
                    or result.get("error_code")
                    or "LEGACY_FAILURE"
                )
            else:
                assert error is None

    assert converted == 76
