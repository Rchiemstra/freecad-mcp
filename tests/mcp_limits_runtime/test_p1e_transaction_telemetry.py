"""P1E helper-safe doubles: pin current compatible-tree transaction telemetry.

D-09 / F-04 remain OPEN OBSERVABILITY_GAP — these tests document what the helper
layer exposes today without closing the product gap. Timeout/cancel outcomes are
covered by ``test_c1c_gui_timeout_outcomes.py`` (not duplicated here).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from freecad_mcp._shared.protocol.pad_feature_contract import (
    PadName,
    make_pad_feature_failure,
    make_pad_feature_success,
)
from freecad_mcp._shared.protocol.set_expression_contract import (
    make_set_expression_failure,
    make_set_expression_success,
)
from freecad_mcp._shared.protocol.sketch_add_constraint_contract import (
    SketchName,
    make_sketch_add_constraint_failure,
    make_sketch_add_constraint_success,
)
from freecad_mcp.operations import (
    run_transaction_operation,
    validate_movement_follow_operation,
)
from freecad_mcp.operations.core_ops.execute_ops import execute_code_operation
from freecad_mcp.operations.parametric_ops.pad_feature import pad_feature_operation
from freecad_mcp.operations.parametric_ops.set_expression import (
    set_expression_operation,
)
from freecad_mcp.operations.parametric_ops.sketch_add_constraint import (
    sketch_add_constraint_operation,
)
from freecad_mcp.responses.tool_results import json_response

pytestmark = pytest.mark.unit


def _partial_evidence(operation: str, document: str = "Model") -> dict:
    """Addon ``_unknown_mutation_evidence`` shape (partial coverage, no rollback)."""
    return {
        "transaction": {
            "status": "unavailable",
            "enabled": False,
            "documents": [document],
            "started": False,
            "committed": False,
            "abort_attempted": False,
            "abort_succeeded": None,
            "abort_errors": [],
            "rollback_attempted": False,
            "rollback_succeeded": None,
            "coverage": "partial",
        },
        "mutation_scope": {
            "declared_documents": [document],
            "expected_modified_objects": [],
            "transaction_coverage": "partial",
            "rollback_policy": "none",
            "operation": operation,
        },
    }


def _assert_typed_no_campaign_transaction(envelope: dict) -> None:
    assert "transaction" not in envelope
    assert envelope["layers"]["transaction_status"] == "not_applicable"
    mutation_scope = envelope.get("mutation_scope")
    assert mutation_scope is None or (
        mutation_scope.get("transaction_coverage") != "unavailable"
    )


def test_baseline_typed_pad_pins_not_applicable_not_campaign_unavailable() -> None:
    """Would fail if typed pad asserted campaign ``transaction_coverage ==
    unavailable``."""
    conn = MagicMock()
    conn.pad_feature.return_value = make_pad_feature_success(PadName("Pad"), "Pad")
    conn.get_active_screenshot.return_value = None

    response = pad_feature_operation(conn, True, "Doc", "Sketch", "Pad", 5.0)

    _assert_typed_no_campaign_transaction(response.structuredContent)


@pytest.mark.parametrize(
    ("operation", "wire_factory", "call"),
    [
        (
            "pad_feature",
            lambda: make_pad_feature_success(PadName("Pad"), "Pad"),
            lambda conn: pad_feature_operation(
                conn, True, "Doc", "Sketch", "Pad", 5.0
            ),
        ),
        (
            "set_expression",
            lambda: make_set_expression_success("Box", "Box.Length", "10 mm"),
            lambda conn: set_expression_operation(
                conn, True, "Doc", "Box", "Box.Length", "10 mm"
            ),
        ),
        (
            "sketch_add_constraint",
            lambda: make_sketch_add_constraint_success(SketchName("Sketch"), 1),
            lambda conn: sketch_add_constraint_operation(
                conn, True, "Doc", "Sketch", [{"type": "Radius", "geo": 0, "value": 5}]
            ),
        ),
    ],
)
def test_typed_success_has_no_campaign_transaction_object(
    operation: str,
    wire_factory,
    call,
) -> None:
    conn = MagicMock()
    method = getattr(conn, operation)
    method.return_value = wire_factory()
    if operation == "pad_feature":
        conn.get_active_screenshot.return_value = None

    response = call(conn)

    assert response.isError is False
    _assert_typed_no_campaign_transaction(response.structuredContent)


@pytest.mark.parametrize(
    ("operation", "wire_factory", "call"),
    [
        (
            "pad_feature",
            lambda: make_pad_feature_failure(
                "ZERO_MATERIAL_DELTA",
                "kernel rejected pad",
                native_status="Rejected",
                rollback_succeeded=True,
            ),
            lambda conn: pad_feature_operation(
                conn, True, "Doc", "Sketch", "Pad", 5.0
            ),
        ),
        (
            "set_expression",
            lambda: make_set_expression_failure(
                "SET_EXPRESSION_REJECTED",
                "expression rejected",
                native_status="Aborted",
                rollback_succeeded=True,
            ),
            lambda conn: set_expression_operation(
                conn, True, "Doc", "Box", "Box.Length", "bad"
            ),
        ),
        (
            "sketch_add_constraint",
            lambda: make_sketch_add_constraint_failure(
                "SKETCH_CONSTRAINT_REJECTED",
                "constraint rejected",
                native_status="Aborted",
                rollback_succeeded=True,
            ),
            lambda conn: sketch_add_constraint_operation(
                conn, True, "Doc", "Sketch", []
            ),
        ),
    ],
)
def test_typed_rollback_failure_keeps_wire_native_fields_without_campaign_transaction(
    operation: str,
    wire_factory,
    call,
) -> None:
    conn = MagicMock()
    getattr(conn, operation).return_value = wire_factory()

    response = call(conn)

    assert response.isError is True
    envelope = response.structuredContent
    data = envelope["data"]
    assert data["rollback_succeeded"] is True
    assert data["native_status"] in {"Rejected", "Aborted"}
    _assert_typed_no_campaign_transaction(envelope)


def test_execute_code_public_pins_unavailable_coverage_and_none_rollback() -> None:
    conn = MagicMock()
    conn.execute_code.return_value = {
        "success": True,
        "message": "ok",
        "execution_category": "public_execute_code",
        "mutation_scope": {
            "declared_documents": ["Model"],
            "transaction_coverage": "unavailable",
            "rollback_policy": "none",
        },
    }

    response = execute_code_operation(conn, True, "pass")

    envelope = response.structuredContent
    assert envelope["mutation_scope"]["transaction_coverage"] == "unavailable"
    assert envelope["mutation_scope"]["rollback_policy"] == "none"
    assert "transaction" not in envelope
    assert envelope["layers"]["transaction_status"] == "not_applicable"


@pytest.mark.parametrize(
    ("operation", "payload"),
    [
        (
            "save_document",
            {"success": True, "save": {"path": "/tmp/model.FCStd"}},
        ),
        (
            "create_document",
            {"success": True, "document_name": "NewDoc"},
        ),
        (
            "export_stl",
            {"success": True, "path": "/tmp/part.stl", "exported": 1, "faces": 12},
        ),
    ],
)
def test_lifecycle_wire_with_evidence_pins_partial_coverage_unavailable_status(
    operation: str,
    payload: dict,
) -> None:
    wire = {**payload, **_partial_evidence(operation)}
    response = json_response(wire)
    envelope = response.structuredContent

    assert envelope["mutation_scope"]["transaction_coverage"] == "partial"
    assert envelope["mutation_scope"]["rollback_policy"] == "none"
    assert envelope["transaction"]["status"] == "unavailable"
    assert envelope["layers"]["transaction_status"] == "unavailable"


def test_run_transaction_mcp_returns_retired_only() -> None:
    response = run_transaction_operation(
        SimpleNamespace(),
        True,
        "Model",
        "edit",
        "pass",
    )

    envelope = response.structuredContent
    assert envelope["data"]["error_code"] == "RUN_TRANSACTION_RETIRED"
    assert envelope["error_code"] == "RUN_TRANSACTION_RETIRED"
    _assert_typed_no_campaign_transaction(envelope)


def test_validate_movement_follow_rejects_without_mutating() -> None:
    # main restored the public read-only JSON-RPC route (c59fbc8): the call reaches
    # FreeCAD's validate_movement_follow, never execute_code, and a malformed reply
    # is an error rather than a success.
    conn = MagicMock()

    response = validate_movement_follow_operation(
        conn,
        True,
        "Model",
        "Source",
        ["Dependent"],
        [1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0],
        15.0,
    )

    assert response.isError is True
    envelope = response.structuredContent
    assert envelope["data"]["error_code"] == "INVALID_RPC_RESPONSE"
    conn.validate_movement_follow.assert_called_once()
    conn.execute_code.assert_not_called()
    _assert_typed_no_campaign_transaction(envelope)
