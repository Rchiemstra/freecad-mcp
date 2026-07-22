"""Bridge FreeCAD core DocumentMutationAuthority with document leases.

Capabilities are short-lived and in-process only. Out-of-process MCP clients
continue to present lease credentials; after lease authorization the addon opens
a core capability for the duration of the GUI-thread mutation.

On FreeCAD builds without the mutation-authority API this module is a no-op so
cooperative observer fencing remains the fallback.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager, nullcontext
from typing import Any, Iterator, Mapping, Sequence

logger = logging.getLogger("FreeCADMCP.document_lease.core_authority")

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


def core_authority_available(document: Any | None = None) -> bool:
    """Return True when FreeCAD exposes the mutation-authority Python API."""

    if document is not None:
        return callable(getattr(document, "openMutationCapability", None))
    try:
        import FreeCAD  # type: ignore

        doc_type = getattr(FreeCAD, "Document", None)
        if doc_type is not None and callable(
            getattr(doc_type, "openMutationCapability", None)
        ):
            return True
        active = getattr(FreeCAD, "ActiveDocument", None)
        if active is not None:
            return callable(getattr(active, "openMutationCapability", None))
    except Exception:
        return False
    return False


def resolve_document(document_or_name: Any) -> Any | None:
    if document_or_name is None:
        return None
    if hasattr(document_or_name, "openMutationCapability") or hasattr(
        document_or_name, "Name"
    ):
        # Prefer objects that look like FreeCAD documents.
        if callable(getattr(document_or_name, "openMutationCapability", None)) or hasattr(
            document_or_name, "Objects"
        ):
            return document_or_name
    try:
        import FreeCAD  # type: ignore

        return FreeCAD.getDocument(str(document_or_name))
    except Exception:
        return None


def set_mcp_owner(
    document: Any,
    *,
    generation: int,
    provider_id: str = "freecad-mcp",
) -> bool:
    """Mark a document as MCP-owned in core. Soft-no-op if API missing."""

    doc = resolve_document(document)
    if doc is None or not callable(getattr(doc, "setMutationOwner", None)):
        return False
    try:
        doc.setMutationOwner("mcp", int(generation), str(provider_id))
        return True
    except Exception:
        logger.warning("setMutationOwner failed", exc_info=True)
        return False


def clear_owner(document: Any) -> bool:
    doc = resolve_document(document)
    if doc is None or not callable(getattr(doc, "clearMutationOwner", None)):
        return False
    try:
        doc.clearMutationOwner()
        return True
    except Exception:
        logger.warning("clearMutationOwner failed", exc_info=True)
        return False


def bump_takeover(document: Any) -> int | None:
    doc = resolve_document(document)
    if doc is None or not callable(getattr(doc, "bumpMutationGeneration", None)):
        return None
    try:
        return int(doc.bumpMutationGeneration())
    except Exception:
        logger.warning("bumpMutationGeneration failed", exc_info=True)
        return None


def authority_status(document: Any) -> dict[str, Any] | None:
    doc = resolve_document(document)
    if doc is None or not callable(getattr(doc, "mutationAuthorityStatus", None)):
        return None
    try:
        status = doc.mutationAuthorityStatus()
        return dict(status) if isinstance(status, Mapping) else None
    except Exception:
        logger.warning("mutationAuthorityStatus failed", exc_info=True)
        return None


def is_core_enforced(document: Any) -> bool:
    status = authority_status(document)
    return bool(status and status.get("restricted"))


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


@contextmanager
def open_mutation_capability(
    document: Any,
    *,
    generation: int,
    kinds: Sequence[str] | None = None,
) -> Iterator[Any]:
    """Open an in-process core capability for the calling thread."""

    doc = resolve_document(document)
    if doc is None or not callable(getattr(doc, "openMutationCapability", None)):
        yield None
        return
    kind_list = list(kinds) if kinds is not None else list(LIVE_MUTATION_KINDS)
    if not kind_list:
        yield None
        return
    capsule = None
    try:
        capsule = doc.openMutationCapability(kind_list, int(generation))
        yield capsule
    finally:
        # Capsule destructor releases the TLS capability scope.
        del capsule


@contextmanager
def open_documents_mutation_capability(
    documents: Sequence[Any],
    *,
    generations: Mapping[Any, int] | Sequence[int] | int,
    kinds: Sequence[str] | None = None,
) -> Iterator[list[Any]]:
    """Open capabilities for one or more documents; release in reverse order."""

    from contextlib import ExitStack

    docs = [resolve_document(doc) for doc in documents]
    docs = [doc for doc in docs if doc is not None]
    if not docs:
        yield []
        return

    if isinstance(generations, int):
        gen_map = {id(doc): int(generations) for doc in docs}
    elif isinstance(generations, Mapping):
        gen_map = {}
        for doc in docs:
            key = getattr(doc, "Name", doc)
            gen_map[id(doc)] = int(generations.get(key, generations.get(doc, 0)))
    else:
        gen_list = list(generations)
        gen_map = {
            id(doc): int(gen_list[i] if i < len(gen_list) else 0)
            for i, doc in enumerate(docs)
        }

    with ExitStack() as stack:
        capsules: list[Any] = []
        for doc in docs:
            generation = gen_map.get(id(doc), 0)
            capsules.append(
                stack.enter_context(
                    open_mutation_capability(doc, generation=generation, kinds=kinds)
                )
            )
        yield capsules


def sync_owner_from_lease_record(document: Any, record: Any) -> bool:
    """Apply MCP ownership from a lease record after acquire/authorize."""

    if record is None:
        return False
    generation = int(getattr(record, "generation", 0) or 0)
    provider = "freecad-mcp"
    owner = getattr(record, "owner", None)
    if owner is not None:
        provider = str(
            getattr(owner, "mcp_instance_id", None)
            or getattr(owner, "agent_id", None)
            or provider
        )
    state = getattr(getattr(record, "state", None), "value", getattr(record, "state", ""))
    if str(state) in {"USER_INTERVENED", "user_intervened"}:
        return bump_takeover(document) is not None
    return set_mcp_owner(document, generation=generation, provider_id=provider)


def sync_clear_from_release(document: Any) -> bool:
    return clear_owner(document)


def capability_context_or_null(
    document: Any,
    *,
    generation: int,
    kinds: Sequence[str] | None = None,
):
    """Return a capability context manager, or nullcontext when unavailable."""

    doc = resolve_document(document)
    if doc is None or not callable(getattr(doc, "openMutationCapability", None)):
        return nullcontext(None)
    return open_mutation_capability(doc, generation=generation, kinds=kinds)
