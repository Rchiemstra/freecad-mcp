"""D-22: an MCP tool call with an argument the tool does not declare must be rejected.

FastMCP's argument models ignore extra keys, so a misspelled optional argument
(``lenght=10``) was silently dropped and the tool ran with its default. The call is now
refused before the tool runs, naming the unknown and the accepted arguments.
"""

from __future__ import annotations

import asyncio

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import CallToolResult, TextContent

from freecad_mcp.instrumented_server import InstrumentedFastMCP
from freecad_mcp.instrumented_server_ops.facade_bindings import bind_instrumented_fast_mcp
from tests.volume.test_measure_volume_json_rpc_contract import (
    _DEFAULT_ARGUMENTS,
    _invoke,
    _RecordingFreeCADTransport,
)

pytestmark = pytest.mark.unit


def _probe_server(calls: list[float]) -> InstrumentedFastMCP:
    bind_instrumented_fast_mcp(InstrumentedFastMCP)
    mcp = InstrumentedFastMCP("d22-probe")

    @mcp.tool()
    def probe(doc_name: str, length: float = 1.0) -> CallToolResult:
        calls.append(length)
        envelope = {
            "schema_version": 1, "status": "succeeded", "operation": "probe",
            "message": f"{doc_name}:{length}", "error": None, "error_code": None,
            "correlation": {}, "layers": {}, "data": {"length": length},
        }
        return CallToolResult(
            content=[TextContent(type="text", text=envelope["message"])],
            structuredContent=envelope,
        )

    return mcp


def _call(mcp: InstrumentedFastMCP, arguments: dict[str, object]):
    async def invoke():
        async with create_connected_server_and_client_session(mcp._mcp_server) as client:
            return await client.call_tool("probe", arguments)

    return asyncio.run(invoke())


def _text(result) -> str:
    return " ".join(getattr(item, "text", "") for item in result.content)


def test_misspelled_optional_argument_is_rejected_before_the_tool_runs():
    calls: list[float] = []
    result = _call(_probe_server(calls), {"doc_name": "D", "lenght": 10})

    assert result.isError is True
    assert "lenght" in _text(result)
    assert "length" in _text(result)
    assert calls == []


def test_declared_arguments_still_run_the_tool():
    calls: list[float] = []
    result = _call(_probe_server(calls), {"doc_name": "D", "length": 10})

    assert result.isError is False
    assert calls == [10.0]


def test_real_tool_with_an_unknown_argument_sends_nothing_to_freecad(monkeypatch):
    transport = _RecordingFreeCADTransport()
    result = _invoke(monkeypatch, transport, {**_DEFAULT_ARGUMENTS, "units": "cm"})

    assert result.isError is True
    assert "units" in _text(result)
    assert transport.requests == []
