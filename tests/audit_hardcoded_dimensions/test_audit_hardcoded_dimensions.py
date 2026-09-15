"""Unit coverage for the typed ``audit_hardcoded_dimensions`` query slice."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import diagnostics_io_actions
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.audit_hardcoded_dimensions import run_audit_hardcoded_dimensions
from tests.typed_rpc_fakes import FakeDocument, FakeObject, collaborators

pytestmark = pytest.mark.unit


def test_audit_hardcoded_dimensions_observed_without_native_mutation():
    events: list[str] = []
    document = FakeDocument(events)
    document.objects["Body"] = FakeObject("Body")
    collab, _api = collaborators(document, events)
    payload = {
        "ok": True,
        "body": "Body",
        "count": 0,
        "findings": [],
    }
    with patch.object(diagnostics_io_actions, "audit_hardcoded_dimensions", return_value=payload):
        result = run_audit_hardcoded_dimensions(collab, "Doc", "Body", True)

    assert result["success"] is True
    assert result["outcome"] == "observed"
    assert "commit" not in events


def test_missing_document_is_rejected():
    events: list[str] = []
    collab, _api = collaborators(None, events)

    result = run_audit_hardcoded_dimensions(collab, "Doc", "Body", True)

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"


def test_missing_object_is_rejected():
    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)

    result = run_audit_hardcoded_dimensions(collab, "Doc", "Body", True)

    assert result["success"] is False
    assert result["error_code"] == "OBJECT_NOT_FOUND"
