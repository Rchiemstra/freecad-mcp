"""Frozen compatibility adapters for removed MCP core mutation authority.

Native FreeCAD collaboration owns document authority after the Phase 18
cutover.  Prior import paths remain available so callers receive
deterministic deprecation behavior instead of exercising core mutation
ownership or capability APIs.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager, nullcontext
from typing import Any

logger = logging.getLogger("FreeCADMCP.document_lease.core_authority")

CLOSE_MUTATION_KINDS: tuple[str, ...] = (
    "Close",
    "PropertyWrite",
    "TransactionOpen",
    "TransactionCommit",
    "TransactionAbort",
)

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


def _legacy_lease_authority_removed() -> dict[str, object]:
    return {
        "success": False,
        "ok": False,
        "error_code": "LEGACY_LEASE_AUTHORITY_REMOVED",
        "error": "Document authority is owned by native FreeCAD collaboration.",
    }


def core_authority_available(document: Any | None = None) -> bool:
    del document
    return False


def core_owner_api_available(document: Any) -> bool:
    del document
    return False


def resolve_document(document_or_name: Any) -> Any | None:
    del document_or_name
    return None


def kinds_for_rpc_method(
    method_name: str, rpc_kind: str | None = None
) -> tuple[str, ...]:
    del method_name, rpc_kind
    return ()


def set_mcp_owner(
    document: Any,
    *,
    generation: int,
    provider_id: str = "freecad-mcp",
) -> bool:
    del document, generation, provider_id
    return False


def clear_owner(document: Any) -> bool:
    del document
    return False


def bump_takeover(document: Any) -> int | None:
    del document
    return None


def authority_status(document: Any) -> dict[str, Any] | None:
    del document
    return None


def is_core_enforced(document: Any) -> bool:
    del document
    return False


@contextmanager
def open_mutation_capability(
    document: Any,
    *,
    generation: int,
    kinds: Sequence[str] | None = None,
) -> Iterator[Any]:
    del document, generation, kinds
    yield None


@contextmanager
def open_documents_mutation_capability(
    documents: Sequence[Any],
    *,
    generations: Mapping[Any, int] | Sequence[int] | int,
    kinds: Sequence[str] | None = None,
) -> Iterator[list[Any]]:
    del documents, generations, kinds
    yield []


def capability_context_or_null(
    document: Any,
    *,
    generation: int,
    kinds: Sequence[str] | None = None,
):
    del document, generation, kinds
    return nullcontext(None)


def sync_owner_from_lease_record(document: Any, record: Any) -> bool:
    del document, record
    return False


def sync_mcp_owner_verified(document: Any, record: Any) -> bool:
    del document, record
    return False


def restore_authority_status(
    document: Any, status: Mapping[str, Any] | None
) -> bool:
    del document, status
    return False


def sync_clear_from_release(document: Any) -> bool:
    del document
    return False


def sync_gui_lease_takeover(document: Any) -> bool:
    del document
    return False


__all__ = [
    "CLOSE_MUTATION_KINDS",
    "LIVE_MUTATION_KINDS",
    "SAVE_MUTATION_KINDS",
    "authority_status",
    "bump_takeover",
    "capability_context_or_null",
    "clear_owner",
    "core_authority_available",
    "core_owner_api_available",
    "is_core_enforced",
    "kinds_for_rpc_method",
    "logger",
    "open_documents_mutation_capability",
    "open_mutation_capability",
    "resolve_document",
    "restore_authority_status",
    "set_mcp_owner",
    "sync_clear_from_release",
    "sync_gui_lease_takeover",
    "sync_mcp_owner_verified",
    "sync_owner_from_lease_record",
]
