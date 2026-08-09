"""Frozen contract snapshot for the FastMCP tool registry."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

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
    assert manager is not None
    registry = getattr(manager, "_tools", None) or getattr(manager, "tools", None)
    assert isinstance(registry, dict)
    return registry


def _capture_tools(mcp) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for name in sorted(_tool_registry(mcp)):
        tool = _tool_registry(mcp)[name]
        fn = getattr(tool, "fn", None) or getattr(tool, "function", None)
        assert fn is not None, f"missing callable for tool {name!r}"
        out[name] = {
            "signature": str(inspect.signature(fn)),
            "docstring": inspect.getdoc(fn) or "",
        }
    return out


@pytest.fixture(scope="module")
def server_module():
    bootstrap_unit_test_runtime()
    from freecad_mcp import server

    return server


def test_mcp_tool_registry_matches_contract_snapshot(server_module):
    expected = _load_snapshot()["tools"]
    actual = _capture_tools(server_module.mcp)
    assert actual == expected


def test_mcp_tool_registry_exposes_expected_tool_count(server_module):
    snapshot = _load_snapshot()
    registry = _tool_registry(server_module.mcp)
    assert len(registry) == snapshot["tool_count"]
    assert frozenset(registry) == frozenset(snapshot["tools"])
    assert list(registry) == snapshot["tool_order"]


def test_mcp_tool_registration_module_order_matches_contract_snapshot():
    from freecad_mcp.tools_register_order import REGISTER_TOOL_MODULES

    assert list(REGISTER_TOOL_MODULES) == _load_snapshot()["register_order"]
