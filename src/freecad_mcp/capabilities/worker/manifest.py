"""Capability manifest for worker (bootstrapped)."""

# ruff: noqa: E501
from __future__ import annotations

from ..schema import ExecutionMode, MutationClass, SubjectManifest, ToolEntry

MANIFEST = SubjectManifest(
    subject="worker",
    register_modules=('tools_worker',),
    tools=(
        ToolEntry(
            name="cancel_worker_job",
            docstring='Cancel a pending worker job or terminate the active worker process tree.',
            signature="(ctx: 'Context', job_id: 'str') -> 'CallToolResult'",
            operation_path="freecad_mcp.capabilities.gateway_refs.connection:cancel_worker_job",
            rpc_method="cancel_worker_job",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.MUTATION,
            register_module="tools_worker",
        ),
        ToolEntry(
            name="get_worker_status",
            docstring='Report isolated FreeCADCmd availability and whether a worker job is active.\n\nReturns JSON with:\n- ``state``: ``idle`` | ``busy`` | ``unavailable``\n- ``busy``: true while a FreeCADCmd job is running\n- ``active_job_id`` / ``pending_job_ids`` / ``queue_depth``\n- ``available``, ``version``, ``executable``, ``last_error``',
            signature="(ctx: 'Context') -> 'CallToolResult'",
            operation_path="freecad_mcp.capabilities.gateway_refs.connection:get_worker_status",
            rpc_method="get_worker_status",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.READ,
            register_module="tools_worker",
        ),
    ),
)
