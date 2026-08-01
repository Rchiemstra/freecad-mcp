"""Lease-record synchronization with core mutation authority."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from .document import core_owner_api_available, resolve_document
from .owner import (
    authority_status,
    bump_takeover,
    clear_owner,
    set_mcp_owner,
)

logger = logging.getLogger("FreeCADMCP.document_lease.core_authority")


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


def sync_mcp_owner_verified(document: Any, record: Any) -> bool:
    """Install and verify the exact MCP fence represented by ``record``.

    Stock FreeCAD builds have no core authority API and remain soft-compatible.
    When the API is present, success requires a readable status reporting the
    replacement owner, generation, and provider exactly; a swallowed Python
    binding failure must never be mistaken for a completed lease handoff.
    """

    doc = resolve_document(document)
    if doc is None:
        return False
    if not core_owner_api_available(doc):
        return True
    if record is None:
        return False
    generation = int(getattr(record, "generation", 0) or 0)
    owner = getattr(record, "owner", None)
    provider = str(
        getattr(owner, "mcp_instance_id", None)
        or getattr(owner, "agent_id", None)
        or "freecad-mcp"
    )
    if generation <= 0:
        return False
    if not set_mcp_owner(
        doc,
        generation=generation,
        provider_id=provider,
    ):
        return False
    status = authority_status(doc)
    return bool(
        status
        and str(status.get("owner") or "").casefold() == "mcp"
        and status.get("restricted") is True
        and int(status.get("generation") or 0) == generation
        and str(status.get("provider_id") or "") == provider
    )


def restore_authority_status(document: Any, status: Mapping[str, Any] | None) -> bool:
    """Best-effort restore of a previously captured core authority status."""

    doc = resolve_document(document)
    if doc is None:
        return False
    if not core_owner_api_available(doc):
        return True
    if not isinstance(status, Mapping):
        return False
    owner = str(status.get("owner") or "").casefold()
    generation = int(status.get("generation") or 0)
    provider = str(status.get("provider_id") or "")
    try:
        if owner == "unrestricted":
            doc.clearMutationOwner()
        elif owner in {"mcp", "user"}:
            doc.setMutationOwner(owner, generation, provider)
        else:
            return False
    except Exception:
        logger.warning("restoring mutation authority status failed", exc_info=True)
        return False
    restored = authority_status(doc)
    if not restored:
        return False
    if str(restored.get("owner") or "").casefold() != owner:
        return False
    if owner == "unrestricted":
        return (
            restored.get("restricted") is False
            and int(restored.get("generation") or 0) == 0
        )
    return bool(
        int(restored.get("generation") or 0) == generation
        and str(restored.get("provider_id") or "") == provider
        and restored.get("restricted") is (owner == "mcp")
    )


def sync_clear_from_release(document: Any) -> bool:
    return clear_owner(document)


def sync_gui_lease_takeover(document: Any) -> bool:
    """Rotate/fence the MCP lease for a GUI Take Over without bumping core.

    Core ``DocumentMutationAuthority.takeover`` is applied by the C++ dialog
    after this returns successfully, so lease and core cannot split.
    """

    doc = resolve_document(document)
    if doc is None:
        return False
    try:
        from document_lease.observer import get_runtime_service
    except ImportError:
        try:
            from addon.FreeCADMCP.document_lease.observer import (  # type: ignore
                get_runtime_service,
            )
        except ImportError:
            # Addon present without observer helpers: allow core-only takeover.
            return True
    try:
        service = get_runtime_service()
        if service is None:
            return True
        identities = getattr(service, "identity_service", None)
        if identities is None:
            return True
        try:
            identity = identities.register_document(doc)
        except Exception:
            identity = identities.resolve(
                {"document_name": str(getattr(doc, "Name", "") or "")}
            )
        dirty = bool(getattr(doc, "Modified", False))
        service.takeover(
            identity.session_uuid,
            dirty=dirty,
            reason="GUI mutation takeover dialog",
        )
        return True
    except Exception:
        logger.warning("sync_gui_lease_takeover failed", exc_info=True)
        return False
