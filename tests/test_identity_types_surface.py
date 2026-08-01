"""Regression tests for identity type extraction (workstream 1F)."""

from __future__ import annotations

import pytest

from addon.FreeCADMCP.document_lease import identity as identity_mod

pytestmark = pytest.mark.unit


def test_identity_public_import_surface() -> None:
    """Identity re-exports moved errors with legacy module names."""

    public_errors = (
        "DocumentIdentityError",
        "UnknownDocumentError",
        "DuplicateDocumentError",
        "IdentityMismatchError",
    )
    for name in public_errors:
        assert hasattr(identity_mod, name), name
        error_type = getattr(identity_mod, name)
        assert error_type.__module__ == "document_lease.identity", name
