"""Mutation-kind constants and RPC method mapping."""

from __future__ import annotations

# Broad mask for live MCP mutations (matches App::MutationKindAll bit layout).
LIVE_MUTATION_KINDS: tuple[str, ...] = (
    "PropertyWrite",
    "AddObject",
    "RemoveObject",
    "Recompute",
    "Undo",
    "Redo",
    "Save",
    "SaveAs",
    "Close",
    "TransactionOpen",
    "TransactionCommit",
    "TransactionAbort",
    "ImportExport",
    "BulkCopy",
    "StructuralProperty",
)

SAVE_MUTATION_KINDS: tuple[str, ...] = (
    "Save",
    "SaveAs",
    "PropertyWrite",
    "TransactionOpen",
    "TransactionCommit",
    "TransactionAbort",
)

CLOSE_MUTATION_KINDS: tuple[str, ...] = (
    "Close",
    "PropertyWrite",
    "TransactionOpen",
    "TransactionCommit",
    "TransactionAbort",
)


def kinds_for_rpc_method(method_name: str, rpc_kind: str | None = None) -> tuple[str, ...]:
    name = str(method_name or "")
    kind = str(rpc_kind or "").lower()
    if name in {"save_document", "save_document_as", "finalize_document_edit"} or kind == "save":
        return SAVE_MUTATION_KINDS
    if name in {"close_document"} or kind == "close":
        return CLOSE_MUTATION_KINDS
    if kind in {"read_only", "control"}:
        return ()
    return LIVE_MUTATION_KINDS
