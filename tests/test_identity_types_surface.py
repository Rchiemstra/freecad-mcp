"""Regression tests for identity type extraction (workstream 1F)."""

from __future__ import annotations

import inspect

import pytest

from addon.FreeCADMCP.document_lease import identity as identity_mod
from addon.FreeCADMCP.document_lease.identity import DocumentIdentityService

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


def test_identity_model_type_reexports() -> None:
    """§3.3 shims keep model types importable from identity."""

    for name in (
        "DocumentIdentity",
        "DocumentSelector",
        "FileBaseline",
        "FileIdentity",
    ):
        assert hasattr(identity_mod, name), name


def test_identity_helper_methods_use_self_parameter() -> None:
    """Class-attribute bindings stay inspect.signature friendly."""

    for name in (
        "register_document",
        "registered_session_uuid",
        "refresh_saved_document",
        "resolve",
        "unregister",
        "list_identities",
    ):
        method = getattr(DocumentIdentityService, name)
        params = list(inspect.signature(method).parameters)
        assert params[0] == "self", name
