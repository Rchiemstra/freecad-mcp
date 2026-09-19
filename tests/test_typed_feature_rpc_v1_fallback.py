"""D-25: typed feature tools must reach the addon on an unauthenticated v1 runtime.

Without an authenticated v2 session ``invoke_typed_feature_rpc`` falls back to the v1
proxy. It called ``conn.server.<method>(**params)``, but ``ProxyMethod`` forwards
positional JSON-RPC params only, so all twelve tools (revolve, booleans, chamfer,
fillet, helical sweep, patterns, loft, mirror, sweep) failed client-side with
"ProxyMethod.__call__() got an unexpected keyword argument 'doc_name'" and never sent
the request. The positional params must bind to the addon handler's parameters by name.
"""

from __future__ import annotations

import importlib
import inspect

import pytest

from freecad_mcp.freecad_client_ops import typed_feature_rpc
from freecad_mcp.freecad_client_ops.proxy_method import ProxyMethod

pytestmark = pytest.mark.unit

_ADDON_OPS = "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops"
TYPED_FEATURE_METHODS = tuple(method.__name__ for method in typed_feature_rpc._RPC_METHODS)


class _RecordingLane:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def call(self, method: str, *args: object) -> dict[str, object]:
        self.calls.append((method, args))
        return {"success": True, "method": method}


class _Server:
    def __init__(self, lane: _RecordingLane) -> None:
        self._lane = lane

    def __getattr__(self, name: str) -> ProxyMethod:
        return ProxyMethod(self._lane, name)


class _V1OnlyConnection:
    def __init__(self, lane: _RecordingLane) -> None:
        self.server = _Server(lane)

    def _invoke_mutation_v2(self, *_args: object, **_kwargs: object) -> None:
        return None


def test_all_twelve_typed_feature_tools_are_covered() -> None:
    assert len(TYPED_FEATURE_METHODS) == 12


@pytest.mark.parametrize("method", TYPED_FEATURE_METHODS)
def test_v1_fallback_sends_params_that_bind_to_the_addon_handler(method: str) -> None:
    client = getattr(typed_feature_rpc, method)
    client_params = list(inspect.signature(client).parameters)[1:]  # drop conn
    sample = {name: f"<{name}>" for name in client_params}
    lane = _RecordingLane()

    result = client(_V1OnlyConnection(lane), **sample)

    assert result == {"success": True, "method": method}
    assert len(lane.calls) == 1
    sent_method, sent_args = lane.calls[0]
    assert sent_method == method

    rpc_name, handler = importlib.import_module(f"{_ADDON_OPS}.{method}").TYPED_RPC_HANDLER
    assert rpc_name == method
    bound = inspect.signature(handler).bind(object(), *sent_args)
    bound.arguments.pop(next(iter(inspect.signature(handler).parameters)))  # self
    assert dict(bound.arguments) == sample
