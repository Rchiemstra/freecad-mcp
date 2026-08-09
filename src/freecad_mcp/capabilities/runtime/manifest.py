"""Capability manifest for runtime (bootstrapped)."""

# ruff: noqa: E501
from __future__ import annotations

from ..schema import ExecutionMode, MutationClass, SubjectManifest, ToolEntry

MANIFEST = SubjectManifest(
    subject="runtime",
    register_modules=('tools_runtime_control', 'tools_runtime_info'),
    tools=(
        ToolEntry(
            name="cancel_request",
            docstring='Request cooperative cancellation for an authenticated RPC request.',
            signature="(ctx: 'Context', request_id: 'str') -> 'CallToolResult'",
            operation_path="freecad_mcp.capabilities.legacy_shims.legacy_removed_tool",
            rpc_method="cancel_request",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.MUTATION,
            register_module="tools_runtime_control",
        ),
        ToolEntry(
            name="check_rpc_sync",
            docstring="Verify that the next FreeCAD GUI response belongs to this exact call.\n\nA unique nonce is round-tripped through FreeCAD's GUI task queue. Use this\nafter an execute timeout or before relying on model inspection results. A\ntimeout or nonce mismatch means the queue is not safe for further work.",
            signature="(ctx: 'Context') -> 'CallToolResult'",
            operation_path="freecad_mcp.capabilities.legacy_shims.legacy_removed_tool",
            rpc_method="check_rpc_sync",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.READ,
            register_module="tools_runtime_control",
        ),
        ToolEntry(
            name="claim_acquisition_result",
            docstring='Custody a lost or pending acquire/adopt/create lease credential.\n\nCall after ``get_request_status`` reports ``result_claimable`` (for example\nfollowing an automatic ``LOCKED_ERROR_HANDOFF_PENDING`` handoff or a\ntransport-lost acquisition). This MCP process retains the one-time token;\nthe tool result never includes the raw credential secret.',
            signature="(ctx: 'Context', request_id: 'str') -> 'CallToolResult'",
            operation_path="freecad_mcp.capabilities.legacy_shims.legacy_removed_tool",
            rpc_method="claim_acquisition_result",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.MUTATION,
            register_module="tools_runtime_control",
        ),
        ToolEntry(
            name="get_request_status",
            docstring='Query a timed-out or long-running authenticated request without replaying it.',
            signature="(ctx: 'Context', request_id: 'str') -> 'CallToolResult'",
            operation_path="freecad_mcp.capabilities.legacy_shims.legacy_removed_tool",
            rpc_method="get_request_status",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.READ,
            register_module="tools_runtime_control",
        ),
        ToolEntry(
            name="get_runtime_info",
            docstring='Report exact MCP, addon, FreeCAD, RPC, and isolated-profile identity.',
            signature="(ctx: 'Context') -> 'CallToolResult'",
            operation_path="freecad_mcp.capabilities.inline.tools_runtime_info.get_runtime_info",
            rpc_method="get_runtime_info",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.READ,
            register_module="tools_runtime_info",
        ),
    ),
)
