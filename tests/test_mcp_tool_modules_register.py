"""Validate Phase 7 / 7D extracted tool modules mirror the live registry."""

from __future__ import annotations

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
    from freecad_mcp.tools_register_order import REGISTER_TOOL_MODULE_OBJECTS

    mcp = InstrumentedFastMCP("extracted-tools-test")
    state = ServerState()
    stale_recovery = StaleLeaseRecoveryOrchestrator()
    connection = MagicMock(name="FreeCADConnection")

    for module in REGISTER_TOOL_MODULE_OBJECTS:
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
    from freecad_mcp.tools_register_order import (
        REGISTER_TOOL_MODULE_OBJECTS,
        REGISTER_TOOL_MODULES,
    )

    assert len(extracted_tool_registry) == _load_snapshot()["tool_count"]
    assert len(REGISTER_TOOL_MODULES) >= 30
    assert tuple(
        module.__name__.rsplit(".", maxsplit=1)[-1]
        for module in REGISTER_TOOL_MODULE_OBJECTS
    ) == REGISTER_TOOL_MODULES


def test_registration_consumes_explicit_module_objects_in_order():
    from types import ModuleType

    from freecad_mcp.server_ops.tool_registration import register_tool_modules

    calls: list[str] = []

    def tool_module(name: str) -> ModuleType:
        module = ModuleType(name)

        def register(mcp, **dependencies):
            calls.append(name)
            assert mcp == "mcp"
            assert dependencies["state"] == "state"
            return {name: dependencies["get_freecad_connection"]}

        module.register = register
        return module

    first = tool_module("first")
    second = tool_module("second")
    selector = object()
    exports = register_tool_modules(
        "mcp",
        modules=(first, second),
        state="state",
        get_freecad_connection=lambda: "connection",
        stale_recovery="recovery",
        document_selector_input=selector,
    )

    assert calls == ["first", "second"]
    assert first.DocumentSelectorInput is selector
    assert second.DocumentSelectorInput is selector
    assert list(exports) == ["first", "second"]


def test_registration_keeps_historic_module_names_keyword(monkeypatch):
    from types import ModuleType

    from freecad_mcp.server_ops import tool_registration

    module = ModuleType("historic")
    module.register = lambda _mcp, **_dependencies: {"historic": object()}
    monkeypatch.setattr(tool_registration, "REGISTER_TOOL_MODULES", ("historic",))
    monkeypatch.setattr(tool_registration, "REGISTER_TOOL_MODULE_OBJECTS", (module,))

    exports = tool_registration.register_tool_modules(
        "mcp",
        module_names=("historic",),
        state="state",
        get_freecad_connection=lambda: None,
        stale_recovery="recovery",
        document_selector_input=dict,
    )

    assert list(exports) == ["historic"]
