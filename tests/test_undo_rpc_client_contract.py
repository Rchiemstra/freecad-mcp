"""Client undo/redo must bind Part 3 selector and history head for invoke_v2."""

from __future__ import annotations

from types import MethodType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.recompute_helpers import (
    redo as rpc_redo,
    undo as rpc_undo,
)
from addon.FreeCADMCP.rpc_server.methods.v2_methods_ops.envelope_params import (
    ordered_envelope_params,
)
from freecad_mcp.generated.capabilities.connection_methods.connection_model_ops import (
    redo,
    undo,
)

pytestmark = pytest.mark.unit


def _readiness_entry(doc_name: str = "Doc", **overrides):
    entry = {
        "document": doc_name,
        "ready": True,
        "document_uid": "uid-doc-1",
        "document_instance_id": 7,
        "lifecycle_epoch": 2,
        "document_name": doc_name,
        "undo_count": 3,
        "undo_head": "EditSketch",
        "redo_count": 1,
        "redo_head": "Pad",
    }
    entry.update(overrides)
    return entry


def _mock_conn(*, doc_name: str = "Doc", readiness_entry=None, ready: bool = True):
    conn = MagicMock()
    conn._mcp_instance_id = "mcp-inst-1"
    conn._invoke_mutation_v2 = MagicMock(return_value={"success": True})
    entry = readiness_entry or _readiness_entry(doc_name)
    conn.server.get_mutation_readiness.return_value = {
        "success": True,
        "ready": ready,
        "documents": [entry],
        "reasons": [],
    }
    return conn


def _assert_part3_undo_params(params: dict, entry: dict) -> None:
    assert "doc_name" not in params
    assert params["doc_selector"] == {
        "document_uid": entry["document_uid"],
        "document_instance_id": entry["document_instance_id"],
        "lifecycle_epoch": entry["lifecycle_epoch"],
        "document_name": entry["document_name"],
    }
    assert isinstance(params["operation_id"], str)
    assert params["operation_id"]
    assert params["expected_undo_count"] == entry["undo_count"]
    assert params["expected_undo_head"] == entry["undo_head"]


def _assert_part3_redo_params(params: dict, entry: dict) -> None:
    assert "doc_name" not in params
    assert params["doc_selector"] == {
        "document_uid": entry["document_uid"],
        "document_instance_id": entry["document_instance_id"],
        "lifecycle_epoch": entry["lifecycle_epoch"],
        "document_name": entry["document_name"],
    }
    assert isinstance(params["operation_id"], str)
    assert params["operation_id"]
    assert params["expected_redo_count"] == entry["redo_count"]
    assert params["expected_redo_head"] == entry["redo_head"]


def test_undo_v2_params_bind_to_rpc_undo_signature():
    entry = _readiness_entry()
    conn = _mock_conn(readiness_entry=entry)

    result = undo(conn, "Doc")

    assert result == {"success": True}
    conn._invoke_mutation_v2.assert_called_once()
    method, params = conn._invoke_mutation_v2.call_args.args[:2]
    assert method == "undo"
    _assert_part3_undo_params(params, entry)

    bound = ordered_envelope_params(
        MethodType(rpc_undo, SimpleNamespace()),
        params,
    )
    assert bound == (
        params["doc_selector"],
        params["operation_id"],
        params["expected_undo_count"],
        params["expected_undo_head"],
    )
    conn.server.undo.assert_not_called()


def test_redo_v2_params_bind_to_rpc_redo_signature():
    entry = _readiness_entry()
    conn = _mock_conn(readiness_entry=entry)

    result = redo(conn, "Doc")

    assert result == {"success": True}
    conn._invoke_mutation_v2.assert_called_once()
    method, params = conn._invoke_mutation_v2.call_args.args[:2]
    assert method == "redo"
    _assert_part3_redo_params(params, entry)

    bound = ordered_envelope_params(
        MethodType(rpc_redo, SimpleNamespace()),
        params,
    )
    assert bound == (
        params["doc_selector"],
        params["operation_id"],
        params["expected_redo_count"],
        params["expected_redo_head"],
    )
    conn.server.redo.assert_not_called()


def test_undo_legacy_fallback_uses_part3_positionals():
    entry = _readiness_entry()
    conn = _mock_conn(readiness_entry=entry)
    conn._invoke_mutation_v2.return_value = None
    conn.server.undo.return_value = {"success": True}

    result = undo(conn, "Doc")

    assert result == {"success": True}
    conn.server.undo.assert_called_once_with(
        {
            "document_uid": entry["document_uid"],
            "document_instance_id": entry["document_instance_id"],
            "lifecycle_epoch": entry["lifecycle_epoch"],
            "document_name": entry["document_name"],
        },
        conn._invoke_mutation_v2.call_args.args[1]["operation_id"],
        entry["undo_count"],
        entry["undo_head"],
    )
    assert conn.server.undo.call_args.args[0] != ("Doc",)


@patch("mcp.server.lowlevel.server.request_ctx")
def test_undo_operation_id_is_stable_for_same_mcp_request(request_ctx):
    request_ctx.get.return_value = SimpleNamespace(request_id="req-stable-1")
    entry = _readiness_entry()
    conn = _mock_conn(readiness_entry=entry)

    undo(conn, "Doc")
    first_id = conn._invoke_mutation_v2.call_args.args[1]["operation_id"]
    undo(conn, "Doc")
    second_id = conn._invoke_mutation_v2.call_args.args[1]["operation_id"]

    assert first_id == second_id

    undo(conn, "OtherDoc")
    other_id = conn._invoke_mutation_v2.call_args.args[1]["operation_id"]
    assert other_id != first_id
