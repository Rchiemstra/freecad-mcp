"""Capability manifest for document_history (bootstrapped)."""

# ruff: noqa: E501
from __future__ import annotations

from ..schema import ExecutionMode, MutationClass, SubjectManifest, ToolEntry

MANIFEST = SubjectManifest(
    subject="document_history",
    register_modules=('tools_document_history',),
    tools=(
        ToolEntry(
            name="close_document",
            docstring='Close an open FreeCAD document and free its memory.\n\nUse this for session hygiene when a document is no longer needed.\nUnsaved changes will be lost. Under a document lease, use\n``finalize_document_edit`` for verified save and release before closing.\n\nArgs:\n    doc_name: The document to close.\n\nReturns:\n    A message indicating success or failure.\n\nExamples:\n    ```json\n    {"doc_name": "Part"}\n    ```',
            signature="(ctx: 'Context', doc_name: 'str') -> 'CallToolResult'",
            operation_path="freecad_mcp.operations.close_document_operation",
            rpc_method="close_document",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.MUTATION,
            register_module="tools_document_history",
        ),
        ToolEntry(
            name="get_recompute_log",
            docstring='Return the recompute state of every object in a document.\n\nUse this after a failed pad/pocket/pattern to find out which object is\n\'Invalid\' or \'Error\' without triggering a full recompute. This is a\ncheap read-only query.\n\nArgs:\n    doc_name: The document to inspect.\n\nReturns:\n    JSON list of objects with their name, label, TypeId, state flags,\n    and a \'valid\' boolean. Objects with state \'Invalid\' or \'Error\'\n    are highlighted so you know exactly what needs fixing.\n\nExamples:\n    ```json\n    {"doc_name": "Part"}\n    ```',
            signature="(ctx: 'Context', doc_name: 'str') -> 'CallToolResult'",
            operation_path="freecad_mcp.operations.get_recompute_log_operation",
            rpc_method="get_recompute_log",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.READ,
            register_module="tools_document_history",
        ),
        ToolEntry(
            name="recompute_document",
            docstring='Force FreeCAD to recompute all objects in a document.\n\nUseful after a sequence of property edits that did not trigger an automatic\nrecompute, or after resolving a dependency cycle.\n\nArgs:\n    doc_name: The document to recompute.\n\nReturns:\n    A message indicating success or failure.',
            signature="(ctx: 'Context', doc_name: 'str') -> 'CallToolResult'",
            operation_path="freecad_mcp.operations.recompute_document_operation",
            rpc_method="recompute_document",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.MUTATION,
            register_module="tools_document_history",
        ),
        ToolEntry(
            name="redo",
            docstring='Redo the previously undone operation in a FreeCAD document.\n\nArgs:\n    doc_name: The document to redo in.\n\nReturns:\n    A message indicating success or failure.',
            signature="(ctx: 'Context', doc_name: 'str') -> 'CallToolResult'",
            operation_path="freecad_mcp.operations.redo_operation",
            rpc_method="redo",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.MUTATION,
            register_module="tools_document_history",
        ),
        ToolEntry(
            name="undo",
            docstring='Undo the last operation in a FreeCAD document.\n\nArgs:\n    doc_name: The document to undo in.\n\nReturns:\n    A message indicating success or failure.',
            signature="(ctx: 'Context', doc_name: 'str') -> 'CallToolResult'",
            operation_path="freecad_mcp.operations.undo_operation",
            rpc_method="undo",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.MUTATION,
            register_module="tools_document_history",
        ),
    ),
)
