"""Proven v2 rejections must keep their typed reason through the client.

The general JSON-RPC lane lifts an add-on rejection that proves nothing was
committed out of its JSON-RPC error and returns the flat typed failure. The
authenticated v2 unwrapper only recognised the ``{"result": ...}`` envelope,
so a live GUI turned every validation failure (unknown document, duplicate
name, zero-length pad, ...) into "returned an invalid contract response;
document state requires reconciliation".
"""

from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.body_create_contract import parse_body_create_response
from freecad_mcp._shared.protocol.json_rpc_client import JsonRpcRemoteError
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.freecad_client_ops.proxy_lane import proven_rejection_from_remote_error

pytestmark = pytest.mark.unit

_REQUEST_ID = "df1e0ac2-4847-564b-9428-7a2f1a17cef0"
_RUNTIME_ID = "10641f13-dd5c-4c88-944e-b7d46f7338fd"


def _connection() -> SimpleNamespace:
    return SimpleNamespace(_identity_lock=threading.Lock(), _rpc_session=None)


def _lifted_document_not_found() -> dict[str, object]:
    lifted = proven_rejection_from_remote_error(
        JsonRpcRemoteError(
            -32000,
            "Document 'NoSuchDoc' not found",
            data={
                "contract_version": 1,
                "outcome": "rejected",
                "committed": False,
                "retry_safe": True,
                "error_code": "DOCUMENT_NOT_FOUND",
                "request_id": _REQUEST_ID,
                "addon_runtime_id": _RUNTIME_ID,
            },
        )
    )
    assert lifted is not None
    return lifted


def test_lifted_rejection_keeps_its_typed_reason() -> None:
    unwrapped = FreeCADConnection._unwrap_v2_response(
        _connection(), _lifted_document_not_found()
    )

    result = parse_body_create_response(unwrapped)

    assert result["outcome"] == "rejected"
    assert result["committed"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"
    assert result["error"] == "Document 'NoSuchDoc' not found"


def test_enveloped_result_is_unchanged() -> None:
    inner = {
        "contract_version": 1,
        "success": True,
        "ok": True,
        "outcome": "committed",
        "committed": True,
        "retry_safe": False,
        "body": "Body",
        "label": "Body",
    }

    unwrapped = FreeCADConnection._unwrap_v2_response(
        _connection(),
        {"ok": True, "request_id": _REQUEST_ID, "addon_runtime_id": _RUNTIME_ID, "result": inner},
    )

    assert parse_body_create_response(unwrapped)["outcome"] == "committed"


@pytest.mark.parametrize(
    "response",
    [
        {"ok": False, "request_id": _REQUEST_ID},
        {"ok": False, "outcome": "rejected", "committed": None, "error": "maybe"},
        {"ok": False, "outcome": "uncertain", "committed": False, "error": "maybe"},
    ],
)
def test_unproven_flat_failures_stay_conservative(response) -> None:
    unwrapped = FreeCADConnection._unwrap_v2_response(_connection(), response)

    assert unwrapped["error_code"] == "RPC_V2_ERROR"
