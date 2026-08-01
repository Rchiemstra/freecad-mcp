"""Regression tests for document_lease.service error/DTO import shims."""

from __future__ import annotations

import pytest

from addon.FreeCADMCP.document_lease import service as service_mod

pytestmark = pytest.mark.unit


def test_service_public_error_and_dto_import_surface() -> None:
    """Service re-exports extracted errors/DTOs with legacy __module__ paths."""
    public_symbols = (
        "AuthorizationError",
        "CleanReleaseError",
        "CoordinationError",
        "DirtyAcquisitionError",
        "DirtyAdoptionError",
        "DocumentIdentityRefreshEvent",
        "ForeignRecoveryError",
        "ForeignRecoveryRecord",
        "LeaseConflictError",
        "LeaseGrant",
        "LeaseServiceError",
        "LeaseStateError",
        "LiveDocumentValidationError",
        "LocalRecoveryError",
        "LocalRuntimeIdentity",
        "LockedErrorHandoffRequired",
        "OrphanedForeignRecoveryRequired",
        "OrphanedLocalMcpRecoveryRequired",
        "ProcessLivenessEvidence",
        "SavedForeignRecoveryRequired",
    )
    for name in public_symbols:
        assert hasattr(service_mod, name), name
        symbol = getattr(service_mod, name)
        assert symbol.__module__ == "document_lease.service", name

    assert hasattr(service_mod, "_CancellationContext")
    assert isinstance(service_mod._CancellationContext, type)
