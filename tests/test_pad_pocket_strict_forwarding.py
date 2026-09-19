"""D09-E4: pad/pocket must not forward the client-only ``strict`` flag to the add-on.

``strict`` is enforced client-side (explicit ``body_name`` required). The typed add-on handlers
``rpc_pad_feature`` / ``rpc_pocket_feature`` have no ``strict`` parameter, so the v2 route failed
with a bind TypeError before GUI dispatch, and the v1 route with ``strict=True`` sent 8
positional arguments and was rejected as JSON-RPC ``-32602 Invalid params``.
"""

from __future__ import annotations

import inspect
import threading

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.pad_feature import rpc_pad_feature
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.pocket_feature import rpc_pocket_feature
from freecad_mcp.freecad_client import FreeCADConnection

pytestmark = pytest.mark.unit

HANDLERS = {"pad_feature": rpc_pad_feature, "pocket_feature": rpc_pocket_feature}


class _Server:
    def __init__(self, calls: list) -> None:
        self._calls = calls

    def __getattr__(self, method: str):
        def call(*args, **kwargs):
            self._calls.append(("v1", method, args, kwargs))
            return {"success": True}

        return call


def _connection(calls: list, *, v2: bool) -> FreeCADConnection:
    conn = object.__new__(FreeCADConnection)
    conn._identity_lock = threading.RLock()
    conn.server = _Server(calls)

    def invoke_mutation_v2(method, params, **_kwargs):
        calls.append(("v2", method, (), dict(params)))
        return {"success": True} if v2 else None

    conn._invoke_mutation_v2 = invoke_mutation_v2
    return conn


@pytest.mark.parametrize("method", sorted(HANDLERS))
@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("v2", [False, True])
def test_every_forwarded_call_binds_to_the_addon_handler(method: str, strict: bool, v2: bool) -> None:
    calls: list = []
    conn = _connection(calls, v2=v2)
    getattr(conn, method)("Chair", "Sketch", "Feature", 20.0, "Seat", False, False, strict=strict)

    signature = inspect.signature(HANDLERS[method])
    sent = [call for call in calls if call[1] == method]
    assert sent, "nothing was sent"
    for route, _name, args, params in sent:
        if route == "v2":
            signature.bind(None, **params)
        else:
            signature.bind(None, *args, **params)
