"""Focused safety tests for restoring a leased document in place."""

from __future__ import annotations

import os

import pytest

from addon.FreeCADMCP.rpc_server import snapshot_service
from addon.FreeCADMCP.rpc_server.snapshot_service import (
    SnapshotRestoreError,
    restore_snapshot_in_place_gui,
)


class _FakeDocument:
    def __init__(self, source_path: str):
        object.__setattr__(self, "_initialized", False)
        self.Name = "Model"
        self.FileName = source_path
        self.Modified = False
        self.HasPendingTransaction = False
        self.Transacting = False
        self.Partial = False
        self.Comment = "original"
        self.Objects = []
        self.load_calls: list[str] = []
        self.recompute_calls = 0
        self.load_error: Exception | None = None
        object.__setattr__(self, "_initialized", True)

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)
        if name == "Comment" and getattr(self, "_initialized", False):
            object.__setattr__(self, "Modified", True)

    def load(self, path: str):
        self.load_calls.append(path)
        self.FileName = path
        self.Modified = False
        if self.load_error is not None:
            raise self.load_error

    def recompute(self):
        self.recompute_calls += 1


def _snapshot(tmp_path):
    target = tmp_path / "snapshot.FCStd"
    target.write_bytes(b"x" * 64)
    return target


@pytest.mark.unit
@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits only")
def test_recovery_snapshot_keeps_directory_traversable_and_file_private(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        snapshot_service.FreeCAD,
        "getUserAppDataDir",
        lambda: str(tmp_path),
        raising=False,
    )

    class SnapshotDocument:
        @staticmethod
        def saveCopy(path):
            with open(path, "wb") as handle:
                handle.write(b"snapshot")

    snapshot_id = snapshot_service.create_lease_baseline_snapshot_gui(
        SnapshotDocument()
    )
    recovery = tmp_path / "FreeCADMCPRecovery"
    artifact = snapshot_service.recovery_snapshot_path(snapshot_id)

    assert recovery.stat().st_mode & 0o777 == 0o700
    assert artifact.stat().st_mode & 0o777 == 0o600


@pytest.mark.unit
def test_restore_retains_proxy_source_path_and_requires_save(tmp_path):
    source = tmp_path / "Model.FCStd"
    source.write_bytes(b"source")
    snapshot = _snapshot(tmp_path)
    document = _FakeDocument(str(source))
    proxy_id = id(document)

    result = restore_snapshot_in_place_gui(
        document,
        snapshot,
        expected_document_name="Model",
        expected_source_path=str(source),
        validator=lambda live: {
            "ok": live is document,
            "object_count": len(live.Objects),
        },
    )

    assert id(document) == proxy_id
    assert document.FileName == str(source)
    assert document.Modified is True
    assert document.load_calls == [str(snapshot.resolve())]
    assert document.recompute_calls == 1
    assert result["dirty"] is True
    assert result["source_path"] == str(source)


@pytest.mark.unit
def test_failed_load_restores_authoritative_source_path(tmp_path):
    source = tmp_path / "Model.FCStd"
    source.write_bytes(b"source")
    snapshot = _snapshot(tmp_path)
    document = _FakeDocument(str(source))
    document.load_error = RuntimeError("corrupt snapshot")

    with pytest.raises(SnapshotRestoreError, match="could not load"):
        restore_snapshot_in_place_gui(
            document,
            snapshot,
            expected_document_name="Model",
            expected_source_path=str(source),
        )

    assert document.FileName == str(source)


@pytest.mark.unit
def test_restore_rejects_changed_live_source_before_loading(tmp_path):
    expected = tmp_path / "Model.FCStd"
    unexpected = tmp_path / "Moved.FCStd"
    expected.write_bytes(b"source")
    unexpected.write_bytes(b"other")
    snapshot = _snapshot(tmp_path)
    document = _FakeDocument(str(unexpected))

    with pytest.raises(SnapshotRestoreError, match="source path changed"):
        restore_snapshot_in_place_gui(
            document,
            snapshot,
            expected_document_name="Model",
            expected_source_path=str(expected),
        )

    assert document.load_calls == []


@pytest.mark.unit
def test_restore_rejects_active_transaction(tmp_path):
    source = tmp_path / "Model.FCStd"
    source.write_bytes(b"source")
    document = _FakeDocument(str(source))
    document.HasPendingTransaction = True

    with pytest.raises(SnapshotRestoreError, match="active transaction"):
        restore_snapshot_in_place_gui(
            document,
            _snapshot(tmp_path),
            expected_document_name="Model",
            expected_source_path=str(source),
        )


@pytest.mark.unit
def test_restore_fails_closed_if_document_cannot_be_marked_dirty(tmp_path):
    source = tmp_path / "Model.FCStd"
    source.write_bytes(b"source")
    snapshot = _snapshot(tmp_path)

    class NeverDirty(_FakeDocument):
        def __setattr__(self, name, value):
            object.__setattr__(self, name, value)
            if name == "Modified":
                object.__setattr__(self, "Modified", False)

    document = NeverDirty(str(source))
    with pytest.raises(SnapshotRestoreError, match="Modified=true"):
        restore_snapshot_in_place_gui(
            document,
            snapshot,
            expected_document_name="Model",
            expected_source_path=str(source),
        )
    assert document.FileName == str(source)


@pytest.mark.unit
def test_restore_rejects_symlink_snapshot(tmp_path):
    source = tmp_path / "Model.FCStd"
    source.write_bytes(b"source")
    snapshot = _snapshot(tmp_path)
    link = tmp_path / "linked.FCStd"
    try:
        os.symlink(snapshot, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable")

    with pytest.raises(SnapshotRestoreError, match="symlink"):
        restore_snapshot_in_place_gui(
            _FakeDocument(str(source)),
            link,
            expected_document_name="Model",
            expected_source_path=str(source),
        )
