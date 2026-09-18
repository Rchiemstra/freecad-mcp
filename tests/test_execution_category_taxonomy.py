#!/usr/bin/env python3
"""Unit guards for execution-category taxonomy (AT-3, AT-4)."""

from __future__ import annotations

import pytest
from mcp.types import CallToolResult

from freecad_mcp.generated.capabilities.connection_methods.connection_invoke_v2_helpers import (
    invoke_v2_execution_category,
)
from freecad_mcp.instrumented_server_ops.call_tool_helpers import (
    build_tool_success_completion,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("method", "params"),
    [
        ("spreadsheet_list_aliases", None),
        ("spreadsheet_list_aliases", {}),
        ("spreadsheet_list_aliases", {"doc_name": "MCPLimit_Calib"}),
    ],
)
def test_invoke_v2_execution_category_non_execute_code_is_typed_direct_rpc(
    method: str,
    params: dict[str, object] | None,
) -> None:
    assert invoke_v2_execution_category(method, params) == "typed_direct_rpc"


@pytest.mark.parametrize(
    "params",
    [{}, {"options": "invalid"}, {"options": []}],
)
def test_invoke_v2_execution_category_execute_code_without_valid_options(
    params: dict[str, object],
) -> None:
    assert invoke_v2_execution_category("execute_code", params) == "public_execute_code"


def test_invoke_v2_execution_category_execute_code_generated_operation() -> None:
    params = {"options": {"generated_operation": True}}
    assert (
        invoke_v2_execution_category("execute_code", params)
        == "generated_internal_execute"
    )


def test_invoke_v2_execution_category_execute_code_read_only_worker_analysis() -> None:
    params = {"options": {"read_only": True}}
    assert (
        invoke_v2_execution_category("execute_code", params)
        == "read_only_worker_analysis"
    )


def test_build_tool_success_completion_prefers_structured_execution_category() -> None:
    result = CallToolResult(
        content=[],
        structuredContent={
            "status": "succeeded",
            "execution_category": "generated_internal_execute",
        },
    )
    _, _, payload = build_tool_success_completion(
        name="spreadsheet_list_aliases",
        category="typed_direct_rpc",
        result=result,
    )
    assert payload["execution_category"] == "generated_internal_execute"


def test_build_tool_success_completion_prefers_data_execution_category() -> None:
    result = CallToolResult(
        content=[],
        structuredContent={
            "status": "succeeded",
            "data": {"execution_category": "generated_internal_execute"},
        },
    )
    _, _, payload = build_tool_success_completion(
        name="spreadsheet_list_aliases",
        category="typed_direct_rpc",
        result=result,
    )
    assert payload["execution_category"] == "generated_internal_execute"


def test_build_tool_success_completion_keeps_predicted_without_actual_category() -> None:
    result = CallToolResult(
        content=[],
        structuredContent={"status": "succeeded", "data": {"object_name": "Plate"}},
    )
    _, _, payload = build_tool_success_completion(
        name="create_document",
        category="typed_direct_rpc",
        result=result,
    )
    assert payload["execution_category"] == "typed_direct_rpc"
