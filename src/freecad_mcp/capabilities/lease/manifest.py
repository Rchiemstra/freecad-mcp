"""Capability manifest for lease (bootstrapped)."""

# ruff: noqa: E501
from __future__ import annotations

from ..schema import ExecutionMode, MutationClass, SubjectManifest, ToolEntry

MANIFEST = SubjectManifest(
    subject="lease",
    register_modules=('tools_lease_acquire_a', 'tools_lease_acquire_b', 'tools_lease_lifecycle'),
    tools=(
        ToolEntry(
            name="finalize_document_edit",
            docstring='Run native change-aware Save/Save As, verify a stable live FCStd hash,\nmetadata, required archive members, and CRC, then report finalization.\n\nNo legacy MCP lease is held or released. A save, clean-state, or verification\nfailure returns ``finalized: false`` and keeps automation fail-closed.',
            signature='(ctx: \'Context\', selector: \'DocumentSelectorInput\', save_mode: "Literal[\'save\', \'save_as\', \'first_save\']" = \'save\', destination: \'str\' = \'\', overwrite: \'bool\' = False, expected_destination_sha256: \'str\' = \'\', validation_profile: \'str\' = \'default\') -> \'CallToolResult\'',
            operation_path="freecad_mcp.capabilities.gateway_refs.connection:finalize_document_edit",
            rpc_method="finalize_document_edit",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.LEASE,
            register_module="tools_lease_lifecycle",
        ),
        ToolEntry(
            name="save_document",
            docstring='Run native change-aware Save and verify a stable live FCStd hash, metadata,\nrequired archive members, and CRC. An Unchanged result is also compared with\nthe invocation baseline and does not rewrite the file.\n\nSelect the open document with ``document_name`` or ``canonical_path``; if both\nare supplied, they must identify the same live document.',
            signature="(ctx: 'Context', selector: 'DocumentSelectorInput', validation_profile: 'str' = 'default') -> 'CallToolResult'",
            operation_path="freecad_mcp.capabilities.gateway_refs.connection:save_document",
            rpc_method="save_document",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.LEASE,
            register_module="tools_lease_lifecycle",
        ),
        ToolEntry(
            name="save_document_as",
            docstring='Run native policy-controlled Save As (no-clobber by default) and verify a\nstable live FCStd hash, metadata, required archive members, and CRC. No legacy\nlease aliases are created.\n\nSelect the open document with ``document_name`` or ``canonical_path``; if both\nare supplied, they must identify the same live document. With ``overwrite=True``,\na non-empty ``expected_destination_sha256`` enables native conflict-safe compare-\nand-swap: the destination is replaced only when its verified SHA-256 matches.',
            signature="(ctx: 'Context', selector: 'DocumentSelectorInput', destination: 'str', overwrite: 'bool' = False, expected_destination_sha256: 'str' = '', validation_profile: 'str' = 'default') -> 'CallToolResult'",
            operation_path="freecad_mcp.capabilities.gateway_refs.connection:save_document_as",
            rpc_method="save_document_as",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.LEASE,
            register_module="tools_lease_lifecycle",
        ),
        ToolEntry(
            name="save_document_copy",
            docstring='Run native Save Copy via ``saveCopyWithOutcome`` and verify a stable live\nFCStd hash, metadata, required archive members, and CRC. The canonical\nsavepoint must not move and pending-file state must remain intact.\n\nSave Copy remains available as an extraction path for quarantined or poisoned\ndocuments. Such a result is marked ``recovery_only=true`` and\n``model_state_verified=false``: archive structure and storage durability are\nverified, but the model must be inspected after reopening and the operation\ndoes not clear quarantine.\n\nSelect the open document with ``document_name`` or ``canonical_path``; if both\nare supplied, they must identify the same live document. ``overwrite=False``\nrefuses an existing destination.',
            signature="(ctx: 'Context', selector: 'DocumentSelectorInput', destination: 'str', overwrite: 'bool' = False, validation_profile: 'str' = 'default') -> 'CallToolResult'",
            operation_path="freecad_mcp.capabilities.gateway_refs.connection:save_document_copy",
            rpc_method="save_document_copy",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.LEASE,
            register_module="tools_lease_lifecycle",
        ),
    ),
)
