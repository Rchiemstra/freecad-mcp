"""Unit tests for capability introspection helpers."""

from __future__ import annotations

import pytest

from freecad_mcp.capabilities.introspection import (
    import_operation_symbol,
    operation_path_for_tool,
)
from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _bootstrap() -> None:
    bootstrap_unit_test_runtime()


@pytest.mark.parametrize(
    ("module_name", "tool_name", "expected_suffix"),
    [
        ("tools_sketch_create_1", "sketch_create", "sketch_create_operation"),
        ("tools_advanced_a", "get_dependency_graph", "get_dependency_graph_operation"),
        ("tools_assembly", "create_assembly_joint", "create_assembly_joint_operation"),
    ],
)
def test_operation_path_honors_relative_import_level(
    module_name: str, tool_name: str, expected_suffix: str
) -> None:
    path = operation_path_for_tool(module_name, tool_name)
    assert path == f"freecad_mcp.operations.{expected_suffix}"


def test_import_operation_symbol_resolves_operations_barrel() -> None:
    symbol = import_operation_symbol("freecad_mcp.operations.sketch_create_operation")
    assert callable(symbol)
