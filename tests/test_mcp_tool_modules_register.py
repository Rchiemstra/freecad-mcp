"""Validate Phase 7 / 7D extracted tool modules mirror the live registry."""

from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime

pytestmark = pytest.mark.unit

_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "mcp_tool_registry_contract_snapshot.json"
)


def _load_snapshot() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _tool_registry(mcp) -> dict:
    manager = getattr(mcp, "_tool_manager", None)
    registry = getattr(manager, "_tools", None) or getattr(manager, "tools", None)
    assert isinstance(registry, dict)
    return registry


def _capture_tools(mcp) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for name in sorted(_tool_registry(mcp)):
        tool = _tool_registry(mcp)[name]
        fn = getattr(tool, "fn", None) or getattr(tool, "function", None)
        assert fn is not None
        params = inspect.signature(fn).parameters
        out[name] = {
            "parameter_names": tuple(params),
            "docstring": inspect.getdoc(fn) or "",
        }
    return out


def _expected_from_live_server() -> dict[str, dict[str, object]]:
    bootstrap_unit_test_runtime()
    from freecad_mcp import server

    return _capture_tools(server.mcp)


@pytest.fixture(scope="module")
def extracted_tool_registry():
    bootstrap_unit_test_runtime()
    from freecad_mcp.instrumented_server import InstrumentedFastMCP
    from freecad_mcp.lease_manager import StaleLeaseRecoveryOrchestrator
    from freecad_mcp.server_state import ServerState
    from freecad_mcp.tools_register_order import REGISTER_TOOL_MODULES

    mcp = InstrumentedFastMCP("extracted-tools-test")
    state = ServerState()
    stale_recovery = StaleLeaseRecoveryOrchestrator()
    connection = MagicMock(name="FreeCADConnection")

    for module_name in REGISTER_TOOL_MODULES:
        module = importlib.import_module(f"freecad_mcp.{module_name}")
        module.register(
            mcp,
            state=state,
            get_freecad_connection=lambda: connection,
            stale_recovery=stale_recovery,
        )

    return _capture_tools(mcp)


def test_extracted_modules_match_live_server_surface(extracted_tool_registry):
    expected = _expected_from_live_server()
    assert extracted_tool_registry == expected


def test_extracted_modules_cover_register_order(extracted_tool_registry):
    from freecad_mcp.tools_register_order import REGISTER_TOOL_MODULES

    assert len(extracted_tool_registry) == _load_snapshot()["tool_count"]
    assert len(REGISTER_TOOL_MODULES) >= 30
