"""Capability manifest for diagnostics (bootstrapped)."""

from __future__ import annotations

from ..schema import ExecutionMode, MutationClass, SubjectManifest, ToolEntry

MANIFEST = SubjectManifest(
    subject="diagnostics",
    register_modules=('tools_diagnostics',),
    tools=(
        ToolEntry(
            name="compare_documents",
            docstring='Compare two open documents (e.g. V7 vs V8) via paired geometric state diffs.\n\n``object_pairs`` optional list of ``{"a": "Body", "b": "Body"}`` or\n``["BodyV7", "BodyV8"]``. When omitted, compares all objects by name.',
            signature="(ctx: 'Context', doc_a: 'str', doc_b: 'str', object_pairs: 'list[Any] | None' = None) -> 'CallToolResult'",
            operation_path="freecad_mcp.operations.compare_documents_operation",
            rpc_method="compare_documents",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.READ,
            register_module="tools_diagnostics",
        ),
        ToolEntry(
            name="diagnose_helix",
            docstring='Diagnose a helix/helical-sweep: axis, placement, profile, handedness, pitch/height,\nresult.',
            signature="(ctx: 'Context', doc_name: 'str', helix_name: 'str') -> 'CallToolResult'",
            operation_path="freecad_mcp.operations.diagnose_helix_operation",
            rpc_method="diagnose_helix",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.READ,
            register_module="tools_diagnostics",
        ),
        ToolEntry(
            name="diagnose_pocket",
            docstring='Diagnose a PartDesign Pocket: support/profile, direction, reversed, length, geometry.',
            signature="(ctx: 'Context', doc_name: 'str', pocket_name: 'str') -> 'CallToolResult'",
            operation_path="freecad_mcp.operations.diagnose_pocket_operation",
            rpc_method="diagnose_pocket",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.READ,
            register_module="tools_diagnostics",
        ),
    ),
)
