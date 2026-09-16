"""Worker-thread regression for the authentication-only cancellation lane."""

from __future__ import annotations

import asyncio
import threading
import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.instrumented_server import InstrumentedFastMCP
from freecad_mcp.rpc_session import RpcAuthenticationSession

pytestmark = pytest.mark.unit


def _context() -> SimpleNamespace:
    return SimpleNamespace(
        request_id="protocol-call",
        request_context=SimpleNamespace(meta=None, experimental=None),
    )


def test_cancel_request_uses_control_lane_during_long_sync_tool(monkeypatch):
    server_instance = InstrumentedFastMCP("phase18-worker-boundary")
    monkeypatch.setattr(
        "freecad_mcp.instrumented_server.emit_event",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(server_instance, "get_context", lambda: _context())
    connection = FreeCADConnection(timeout=5)
    rpc_session = RpcAuthenticationSession()
    rpc_session.mark_connected("rpc-session", session_id="session-1")
    connection.configure_lease_routing(rpc_session, lambda _name: None)
    general_started = threading.Event()
    general_release = threading.Event()
    cancel_rpc_calls: list[dict[str, Any]] = []

    def invoke_v2(
        method: str,
        params: dict[str, Any],
        _context: Any,
        *,
        control: bool = False,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del _context, timeout, kwargs
        assert method == "cancel_request"
        assert control is True
        cancel_rpc_calls.append(dict(params))
        return {
            "ok": True,
            "result": {"success": True, "cancellation": {"status": "requested"}},
        }

    connection.invoke_v2 = invoke_v2  # type: ignore[method-assign]
    lane_threads: dict[str, str] = {}

    @server_instance.tool(name="long_execute_code")
    def long_execute_code() -> dict[str, str]:
        lane_threads["general"] = threading.current_thread().name
        general_started.set()
        if not general_release.wait(timeout=5.0):
            raise TimeoutError("long_execute_code was not released")
        return {"status": "done"}

    @server_instance.tool(name="cancel_request")
    def cancel_request_tool(request_id: str) -> dict[str, object]:
        lane_threads["control"] = threading.current_thread().name
        return connection.cancel_request(request_id)

    async def run() -> None:
        general_task = asyncio.create_task(
            server_instance.call_tool("long_execute_code", {})
        )
        deadline = asyncio.get_running_loop().time() + 2.0
        while not general_started.is_set():
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError("long_execute_code did not start")
            await asyncio.sleep(0.01)

        target_request_id = str(uuid.uuid4())
        result = await asyncio.wait_for(
            server_instance.call_tool(
                "cancel_request",
                {"request_id": target_request_id},
            ),
            timeout=1.0,
        )

        assert result["success"] is True
        assert result["cancellation"]["status"] == "requested"
        assert cancel_rpc_calls == [{"target_request_id": target_request_id}]
        assert lane_threads["control"].startswith("mcp-control-tool")
        assert lane_threads["general"].startswith("mcp-sync-tool")
        assert lane_threads["control"] != lane_threads["general"]

        general_release.set()
        await asyncio.wait_for(general_task, timeout=5.0)

    asyncio.run(run())
    connection.disconnect()
