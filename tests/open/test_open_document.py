"""Unit coverage for the typed ``open_document`` lifecycle slice."""

from __future__ import annotations

from pathlib import Path

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.open_document import run_open_document
from tests.typed_rpc_fakes import collaborators

pytestmark = pytest.mark.unit


def test_open_document_verifies_without_native_mutation(tmp_path: Path):
    events: list[str] = []
    collab, api = collaborators(None, events)
    path = tmp_path / "Opened.FCStd"
    path.write_text("stub", encoding="utf-8")

    result = run_open_document(collab, str(path))

    assert result["success"] is True
    assert result["outcome"] == "verified"
    assert "commit" not in events
    assert api.getDocument("Opened") is not None


def test_invalid_path_is_rejected():
    events: list[str] = []
    collab, _api = collaborators(None, events)

    result = run_open_document(collab, "")

    assert result["success"] is False
    assert result["error_code"] == "INVALID_ARGUMENT"
