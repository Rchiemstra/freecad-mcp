"""Unit coverage for the typed ``snapshot`` query slice."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import diagnostics_io_actions
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.snapshot import run_snapshot
from tests.typed_rpc_fakes import FakeDocument, collaborators

pytestmark = pytest.mark.unit


def test_snapshot_observed_without_native_mutation():
    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)
    payload = {"snapshot_id": "snap-1", "doc": "Doc", "count": 2}
    with patch.object(diagnostics_io_actions, "snapshot_document", return_value=payload):
        result = run_snapshot(collab, "Doc")

    assert result["success"] is True
    assert result["outcome"] == "observed"
    assert result["snapshot_id"] == "snap-1"
    assert result["count"] == 2
    assert "commit" not in events


def test_missing_document_is_rejected():
    events: list[str] = []
    collab, _api = collaborators(None, events)

    result = run_snapshot(collab, "Doc")

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"


def test_snapshot_document_records_live_owner_not_only_the_name():
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.diagnostics_io_actions import (
        snapshot_document,
    )

    events: list[str] = []
    document = FakeDocument(events)
    document.Uid = "uid-live"
    document.collaborationIdentity = lambda: {
        "instance_id": 3,
        "lifecycle_epoch": 1,
        "state": "Live",
    }
    document._mcp_snapshots = []

    def save_copy(path: str) -> None:
        Path(path).write_bytes(b"")

    document.saveCopy = save_copy
    payload = snapshot_document(document)

    assert payload["doc"] == "Doc"
    assert document._mcp_snapshots
    row = document._mcp_snapshots[0]
    assert row["id"] == payload["snapshot_id"]
    assert row["document_uid"] == "uid-live"
    assert row["document_instance_id"] == 3
    assert row["doc"] == "Doc"
    Path(str(row["path"])).unlink(missing_ok=True)


def test_snapshot_document_refuses_a_document_without_live_identity():
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.diagnostics_io_actions import (
        snapshot_document,
    )

    document = FakeDocument([])
    document._mcp_snapshots = []
    document.saveCopy = lambda path: Path(path).write_bytes(b"")

    with pytest.raises(RuntimeError, match="collaboration instance id"):
        snapshot_document(document)
    assert document._mcp_snapshots == []


def test_io_failure_is_rejected():
    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)
    with patch.object(diagnostics_io_actions, "snapshot_document", side_effect=RuntimeError("snapshot failed")):
        result = run_snapshot(collab, "Doc")

    assert result["success"] is False
    assert result["error_code"] == "SNAPSHOT_FAILED"
