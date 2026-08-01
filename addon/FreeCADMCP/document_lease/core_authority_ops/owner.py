"""Core mutation-owner read/write helpers."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from .document import resolve_document

logger = logging.getLogger("FreeCADMCP.document_lease.core_authority")


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
