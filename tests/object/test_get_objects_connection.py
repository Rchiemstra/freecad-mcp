"""Connection-layer get_objects JSON-RPC reconstruction."""

from __future__ import annotations

from types import SimpleNamespace

from addon.FreeCADMCP.transport.json_rpc_errors import json_rpc_error_from_result
from freecad_mcp._shared.protocol.get_objects_contract import make_get_objects_failure
from freecad_mcp._shared.protocol.json_rpc_client import JsonRpcRemoteError
from freecad_mcp.generated.capabilities.connection_methods.connection_view_ops import (
    get_objects,
)


def _json_rpc_data(failure: dict[str, object]) -> dict[str, object]:
    rpc_error = json_rpc_error_from_result(failure)
    assert rpc_error is not None
    data = rpc_error["data"]
    assert isinstance(data, dict)
    assert "success" not in data
    assert "ok" not in data
    assert "error" not in data
    return data


def test_connection_get_objects_reconstructs_json_rpc_document_not_found():
    failure = make_get_objects_failure(
        "DOCUMENT_NOT_FOUND",
        "Document not found: 'MissingDoc'",
    )
    data = _json_rpc_data(failure)
    rpc_error = json_rpc_error_from_result(failure)
    assert rpc_error is not None

    def server_get_objects(*_args, **_kwargs):
        raise JsonRpcRemoteError(
            rpc_error["code"],
            rpc_error["message"],
            data=data,
        )

    conn = SimpleNamespace(server=SimpleNamespace(get_objects=server_get_objects))
    result = get_objects(conn, "MissingDoc")
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"
    assert result["success"] is False
    assert result["outcome"] == "rejected"


def test_connection_get_objects_transport_stays_uncertain():
    def server_get_objects(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    conn = SimpleNamespace(server=SimpleNamespace(get_objects=server_get_objects))
    result = get_objects(conn, "Doc")
    assert result["error_code"] == "GET_OBJECTS_TRANSPORT_UNCERTAIN"
    assert result["outcome"] == "uncertain"
