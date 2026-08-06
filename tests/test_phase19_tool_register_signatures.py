"""Phase 19 W2: tool modules accept typed ToolDependencies at registration."""

from __future__ import annotations

import importlib
import inspect
from types import MappingProxyType
from typing import get_type_hints
from unittest.mock import MagicMock

import pytest
from typing_extensions import TypedDict

from freecad_mcp.collaboration_client import CollaborationClient
from freecad_mcp.server_ops.tool_dependencies import ToolDependencies
from freecad_mcp.server_state import ServerState
from freecad_mcp.tools_register_order import REGISTER_TOOL_MODULE_OBJECTS

pytestmark = pytest.mark.unit

_SKIP_MODULES = frozenset(
    {
        "tools_register_order",
        "tools_server_surfaces",
        "tools_types",
    }
)

_SELECTOR_MODULES = frozenset(
    {
        "tools_lease_acquire_a",
        "tools_lease_acquire_b",
        "tools_lease_lifecycle",
    }
)


class _SelectorInput(TypedDict, total=False):
    __pydantic_config__ = MappingProxyType({"extra": "forbid"})

    document_name: str
    document_session_uuid: str
    canonical_path: str


def _dependencies(*, selector: type = _SelectorInput) -> ToolDependencies:
    connection = MagicMock(name="FreeCADConnection")
    return ToolDependencies(
        state=ServerState(),
        get_freecad_connection=lambda: connection,
        recovery_compatibility=object(),
        collaboration=CollaborationClient(connection),
        document_selector_input=selector,
    )


def _owned_tool_modules():
    for module in REGISTER_TOOL_MODULE_OBJECTS:
        name = module.__name__.rsplit(".", maxsplit=1)[-1]
        if name in _SKIP_MODULES:
            continue
        yield pytest.param(module, id=name)


@pytest.mark.parametrize("module", list(_owned_tool_modules()))
def test_register_accepts_tool_dependencies_keyword_only(module):
    signature = inspect.signature(module.register)
    parameters = list(signature.parameters.values())

    assert parameters[0].name == "mcp"
    assert parameters[1].name == "dependencies"
    assert parameters[1].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters[1].annotation in {ToolDependencies, "ToolDependencies"}
    assert "state" not in signature.parameters
    assert "get_freecad_connection" not in signature.parameters
    assert "stale_recovery" not in signature.parameters


@pytest.mark.parametrize("module", list(_owned_tool_modules()))
def test_register_without_module_document_selector_mutation(module):
    fresh = importlib.import_module(module.__name__)
    assert not hasattr(fresh, "DocumentSelectorInput")

    mcp = MagicMock(name="InstrumentedFastMCP")
    dependencies = _dependencies()
    exports = fresh.register(mcp, dependencies=dependencies)

    assert isinstance(exports, dict)
    assert mcp.tool.called
    assert not hasattr(fresh, "DocumentSelectorInput")


@pytest.mark.parametrize(
    "module_name",
    sorted(_SELECTOR_MODULES),
)
def test_selector_modules_bind_document_selector_input_from_dependencies(module_name):
    module = importlib.import_module(f"freecad_mcp.{module_name}")
    assert not hasattr(module, "DocumentSelectorInput")
    assert "from .tools_types import DocumentSelectorInput" not in inspect.getsource(module)

    mcp = MagicMock(name="InstrumentedFastMCP")

    def _tool_decorator(*args, **kwargs):
        if len(args) == 1 and callable(args[0]):
            return args[0]

        def _wrap(tool):
            return tool

        return _wrap

    mcp.tool.side_effect = _tool_decorator

    custom_selector = type(
        "CustomSelectorInput",
        (),
        {"__annotations__": {"document_name": str}},
    )
    dependencies = _dependencies(selector=custom_selector)
    exports = module.register(mcp, dependencies=dependencies)

    selector_tools = [
        name
        for name, tool in exports.items()
        if "selector" in inspect.signature(tool).parameters
    ]
    assert selector_tools

    for name in selector_tools:
        hints = get_type_hints(
            exports[name],
            localns={"DocumentSelectorInput": custom_selector},
        )
        assert hints["selector"] in {custom_selector, custom_selector | None}
