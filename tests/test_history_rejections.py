"""Undo/redo refusals must reach the agent as rejections, not as uncertain.

undo on a misspelled document or an empty history answered "undo response
unavailable: FreeCAD RPC error -32000: ..." with outcome "uncertain", which
tells an agent the document state is unknown although nothing happened.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.redo_contract import parse_redo_response
from freecad_mcp._shared.protocol.undo_contract import parse_undo_response
from freecad_mcp.generated.capabilities.connection_methods import connection_model_ops

pytestmark = pytest.mark.unit


def _connection(readiness):
    return SimpleNamespace(server=SimpleNamespace(get_mutation_readiness=lambda _name: readiness))


@pytest.mark.parametrize(
    "readiness, code",
    [
        ({"success": True, "ready": True, "documents": []}, "DOCUMENT_NOT_FOUND"),
        ({"success": True, "ready": False, "documents": [{}], "reasons": ["recomputing"]},
         "MUTATION_NOT_READY"),
        ({"success": False, "ok": False, "outcome": "rejected", "committed": False,
          "retry_safe": True, "error_code": "DOCUMENT_NOT_FOUND",
          "error": "Document 'NoSuchDoc' not found"}, "DOCUMENT_NOT_FOUND"),
    ],
)
@pytest.mark.parametrize("undo, parse", [(True, parse_undo_response), (False, parse_redo_response)])
def test_preparation_failures_are_rejections(readiness, code, undo, parse):
    prepared = connection_model_ops._prepare_history_mutation(
        _connection(readiness), "NoSuchDoc", undo=undo
    )

    parsed = parse(prepared)

    assert parsed["outcome"] == "rejected", parsed
    assert parsed["error_code"] == code


def _live_history_readiness(*, pending_recompute):
    entry = {
        "document_name": "Drawing", "document_uid": "drawing-uid",
        "document_instance_id": 9, "lifecycle_epoch": 17,
        "undo_count": 2, "undo_head": "MCP: execute_code",
        "redo_count": 0, "redo_head": "",
        "must_execute": pending_recompute, "recomputing": False,
        "diagnostic": "The document has pending recompute work" if pending_recompute else "Ready for mutation",
    }
    return {
        "success": True, "ready": not pending_recompute, "documents": [entry],
        "reasons": ["pending_recompute", "native_not_ready"] if pending_recompute else [],
    }


def test_ready_drawing_history_can_be_prepared():
    prepared = connection_model_ops._prepare_history_mutation(
        _connection(_live_history_readiness(pending_recompute=False)), "Drawing", undo=True
    )
    assert prepared["expected_count"] == 2
    assert prepared["expected_head"] == "MCP: execute_code"
    assert prepared["doc_selector"]["document_name"] == "Drawing"


def test_pending_drawing_recompute_rejection_explains_live_state_and_recovery():
    prepared = connection_model_ops._prepare_history_mutation(
        _connection(_live_history_readiness(pending_recompute=True)), "Drawing", undo=True
    )
    result = parse_undo_response(prepared)
    assert result["error_code"] == "MUTATION_NOT_READY"
    assert result["outcome"] == "rejected"
    assert "pending recompute work" in result["error"]
    assert "Live undo count: 2" in result["error"]
    assert "recompute_document" in result["error"]


def test_transaction_blocker_does_not_suggest_recompute_as_recovery():
    readiness = _live_history_readiness(pending_recompute=True)
    readiness["reasons"].append("native_transaction_in_progress")
    prepared = connection_model_ops._prepare_history_mutation(
        _connection(readiness), "Drawing", undo=True
    )
    result = parse_undo_response(prepared)
    assert result["error_code"] == "MUTATION_NOT_READY"
    assert "native_transaction_in_progress" in result["error"]
    assert "recompute_document" not in result["error"]
