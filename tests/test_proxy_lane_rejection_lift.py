"""D-20: a definite server-side rejection must not be reported as a transport-uncertain outcome.

On RPC v1 the add-on serialises a typed ``{"success": False, "outcome": "rejected",
"committed": False, ...}`` result as a JSON-RPC error, the client raised it, and every operation
wrapped it as ``*_TRANSPORT_UNCERTAIN`` with ``committed: null`` / ``retry_safe: false``
(observed: ``pad_feature(length=-10)`` -> "Pad response unavailable: FreeCAD RPC error -32000").
Authenticated v2 already returns the structured failure; general v1 lanes now do the same.
"""

from __future__ import annotations

import pytest

from addon.FreeCADMCP._shared.protocol.json_rpc import encode_json_rpc_responses, json_rpc_error
from addon.FreeCADMCP.transport.json_rpc_errors import json_rpc_error_from_result
from freecad_mcp._shared.protocol.json_rpc_client import JsonRpcRemoteError
from freecad_mcp.freecad_client_ops import proxy_lane as subject
from freecad_mcp.freecad_client_ops.proxy_lane import ProxyLane

pytestmark = pytest.mark.unit

REJECTED = {
    "contract_version": 1,
    "success": False,
    "ok": False,
    "outcome": "rejected",
    "committed": False,
    "retry_safe": True,
    "error_code": "INVALID_ARGUMENT",
    "error": "length must be a finite number greater than zero",
}
UNCERTAIN = {**REJECTED, "outcome": "uncertain", "committed": None, "retry_safe": False,
             "error_code": "NATIVE_COMMIT_UNKNOWN", "error": "commit state unknown"}


class _Transport:
    def __init__(self, result: dict) -> None:
        self._result = result
        self.extra_headers: list = []

    def request(self, _path, payload, _headers):
        import json

        request_id = json.loads(payload)["id"]
        mapped = json_rpc_error_from_result(self._result)
        body = encode_json_rpc_responses(
            [json_rpc_error(request_id, mapped["code"], mapped["message"], mapped["data"])], batch=False
        )
        return 200, {subject.JSON_RPC_PROTOCOL_HEADER.lower(): (subject.JSON_RPC_PROTOCOL_VALUE,)}, body


def _lane(result: dict, *, lift: bool) -> ProxyLane:
    return ProxyLane("http://127.0.0.1:9875", 5.0, lambda _m, _a: (), transport=_Transport(result), lift_rejections=lift)


def test_general_lane_returns_the_proven_rejection():
    result = _lane(REJECTED, lift=True).call("pad_feature", "Chair", "S", "P", -10)
    assert result["success"] is False
    assert result["outcome"] == "rejected"
    assert result["committed"] is False
    assert result["retry_safe"] is True
    assert result["error_code"] == "INVALID_ARGUMENT"
    assert result["error"] == REJECTED["error"]


def test_uncertain_failures_still_raise_on_general_lane():
    with pytest.raises(JsonRpcRemoteError):
        _lane(UNCERTAIN, lift=True).call("pad_feature", "Chair", "S", "P", 10)


def test_control_lane_keeps_raising():
    with pytest.raises(JsonRpcRemoteError):
        _lane(REJECTED, lift=False).call("handshake_v2", {})


def test_connection_general_lane_opts_in(monkeypatch):
    from freecad_mcp.freecad_client_ops import connection_init

    seen: list[bool] = []
    original = connection_init.ProxyLane

    def recording(*args, **kwargs):
        seen.append(bool(kwargs.get("lift_rejections", False)))
        return original(*args, **kwargs)

    monkeypatch.setattr(connection_init, "ProxyLane", recording)
    from freecad_mcp.freecad_client import FreeCADConnection

    FreeCADConnection(host="127.0.0.1", port=9875)
    assert seen[:2] == [True, False]
