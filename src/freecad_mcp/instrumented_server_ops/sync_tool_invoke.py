"""Invoke synchronous MCP tools with SDK argument validation."""

from __future__ import annotations

from typing import Any


def invoke_sync_tool(tool: Any, arguments: dict[str, Any], context: Any) -> Any:
    """Run one synchronous tool with the MCP SDK's argument validation."""

    metadata = tool.fn_metadata
    context_kwargs = (
        {tool.context_kwarg: context}
        if tool.context_kwarg is not None
        else None
    )
    arguments_pre_parsed = metadata.pre_parse_json(arguments)
    arguments_parsed_model = metadata.arg_model.model_validate(
        arguments_pre_parsed
    )
    arguments_parsed_dict = arguments_parsed_model.model_dump_one_level()
    arguments_parsed_dict |= context_kwargs or {}
    return tool.fn(**arguments_parsed_dict)
