"""Frozen service-operation adapters for removed MCP document authority."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

__all__ = (
    "claim_locked_error_handoff",
    "recover_orphaned_local_mcp_acquisition",
    "release_clean",
)


def _legacy_lease_authority_removed() -> dict[str, object]:
    """Return a fresh result for the removed legacy authority."""

    return {
        "success": False,
        "ok": False,
        "error_code": "LEGACY_LEASE_AUTHORITY_REMOVED",
        "error": "Document authority is owned by native FreeCAD collaboration.",
    }


def claim_locked_error_handoff(
    self,
    selector: DocumentSelector | Mapping[str, Any] | str,  # noqa: F821
    owner: LeaseOwner,  # noqa: F821
    *,
    validation: LiveDocumentValidation,  # noqa: F821
    local_confirmation: bool,
    task_summary: str = "",
) -> dict[str, object]:
    """Return the frozen result for the retired locked-error handoff."""

    del self, selector, owner, validation, local_confirmation, task_summary
    return _legacy_lease_authority_removed()


def recover_orphaned_local_mcp_acquisition(
    self,
    selector: DocumentSelector | Mapping[str, Any] | str,  # noqa: F821
    owner: LeaseOwner,  # noqa: F821
    *,
    validation: LiveDocumentValidation,  # noqa: F821
    snapshot_id: str,
    task_summary: str = "",
    authority_handoff: Callable[[LeaseRecord], bool] | None = None,  # noqa: F821
    authority_rollback: Callable[[], bool] | None = None,
    credential_escrow: Callable[[LeaseGrant], bool] | None = None,  # noqa: F821
) -> dict[str, object]:
    """Return the frozen result for retired local-orphan recovery."""

    del (
        self,
        selector,
        owner,
        validation,
        snapshot_id,
        task_summary,
        authority_handoff,
        authority_rollback,
        credential_escrow,
    )
    return _legacy_lease_authority_removed()


def release_clean(
    self,
    credential: LeaseCredential,  # noqa: F821
    *,
    validation: LiveDocumentValidation,  # noqa: F821
) -> dict[str, Any]:
    """Return the frozen result for the retired clean-release authority."""

    del self, credential, validation
    return _legacy_lease_authority_removed()
