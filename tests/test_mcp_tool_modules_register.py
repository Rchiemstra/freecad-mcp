"""Validate Phase 7 / 7D extracted tool modules mirror the live registry."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from types import MappingProxyType
from unittest.mock import MagicMock

import pytest
from typing_extensions import TypedDict

from freecad_mcp.collaboration_client import CollaborationClient
from freecad_mcp.server_ops.tool_dependencies import ToolDependencies
from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime

pytestmark = pytest.mark.unit

_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "mcp_tool_registry_contract_snapshot.json"
)


class _SelectorInput(TypedDict, total=False):
    __pydantic_config__ = MappingProxyType({"extra": "forbid"})

    document_name: str
    document_session_uuid: str
    canonical_path: str


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


def _dependencies(*, selector: type = _SelectorInput) -> ToolDependencies:
    connection = MagicMock(name="FreeCADConnection")
    return ToolDependencies(
        state=object(),
        get_freecad_connection=lambda: connection,
        recovery_compatibility=None,
        collaboration=CollaborationClient(connection),
        document_selector_input=selector,
    )


def _expected_from_live_server() -> dict[str, dict[str, object]]:
    bootstrap_unit_test_runtime()
    from freecad_mcp import server

    return _capture_tools(server.mcp)


@pytest.fixture(scope="module")
def extracted_tool_registry():
    bootstrap_unit_test_runtime()
    from freecad_mcp.instrumented_server import InstrumentedFastMCP
    from freecad_mcp.tools_register_order import REGISTER_TOOL_MODULE_OBJECTS

    mcp = InstrumentedFastMCP("extracted-tools-test")
    dependencies = _dependencies()

    for module in REGISTER_TOOL_MODULE_OBJECTS:
        module.register(mcp, dependencies=dependencies)

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
    seen: list[ToolDependencies] = []

    def tool_module(name: str) -> ModuleType:
        module = ModuleType(name)

        def register(mcp, *, dependencies: ToolDependencies) -> dict[str, object]:
            calls.append(name)
            seen.append(dependencies)
            assert mcp == "mcp"
            assert dependencies.state == "state"
            return {name: dependencies.get_freecad_connection()}

        module.register = register
        return module

    first = tool_module("first")
    second = tool_module("second")
    selector = _SelectorInput
    connection = MagicMock(name="FreeCADConnection")
    collaboration = CollaborationClient(connection)
    exports = register_tool_modules(
        "mcp",
        modules=(first, second),
        state="state",
        get_freecad_connection=lambda: connection,
        recovery_compatibility=None,
        collaboration=collaboration,
        document_selector_input=selector,
    )

    assert calls == ["first", "second"]
    assert len(seen) == 2
    assert seen[0] is seen[1]
    assert seen[0].collaboration is collaboration
    assert seen[0].document_selector_input is selector
    assert not hasattr(first, "DocumentSelectorInput")
    assert not hasattr(second, "DocumentSelectorInput")
    assert list(exports) == ["first", "second"]


def test_registration_keeps_historic_module_names_keyword(monkeypatch):
    from types import ModuleType

    from freecad_mcp.server_ops import tool_registration

    module = ModuleType("historic")
    module.register = lambda _mcp, *, dependencies: {"historic": dependencies}
    monkeypatch.setattr(tool_registration, "REGISTER_TOOL_MODULES", ("historic",))
    monkeypatch.setattr(tool_registration, "REGISTER_TOOL_MODULE_OBJECTS", (module,))

    connection = MagicMock(name="FreeCADConnection")
    exports = tool_registration.register_tool_modules(
        "mcp",
        module_names=("historic",),
        state="state",
        get_freecad_connection=lambda: connection,
        recovery_compatibility=None,
        collaboration=CollaborationClient(connection),
        document_selector_input=dict,
    )

    assert list(exports) == ["historic"]
