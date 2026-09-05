"""Part 3 Save Copy: canonical savepoint must not move."""

from __future__ import annotations

import inspect
import os
import tempfile
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods import native_lifecycle_methods
from addon.FreeCADMCP.rpc_server.methods.dispatch_helpers_ops import (
    dispatch_core_enforcement_auth,
)
from addon.FreeCADMCP.rpc_server.methods.dispatch_helpers_ops import dispatch_core

pytestmark = pytest.mark.unit


def _write_minimal_fcstd(path: str) -> None:
    import zipfile

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Document.xml", "<Document/>")


def _mock_document(
    *,
    canonical_path: str,
    pending_state: dict | None = None,
    save_copy_outcome: dict | None = None,
):
    pending_state = pending_state or {
        "state": "dirty",
        "has_pending_file_changes": True,
        "last_canonical_save_failed": False,
    }
    document = SimpleNamespace(
        Name="Model",
        FileName=canonical_path,
        Modified=True,
    )

    def get_file_change_state():
        return dict(pending_state)

    document.getFileChangeState = get_file_change_state
    document.hasPendingFileChanges = lambda: bool(
        pending_state.get("has_pending_file_changes", False)
    )

    def save_copy_with_outcome(destination: str):
        if save_copy_outcome is not None:
            return dict(save_copy_outcome)
        dest = os.path.realpath(destination)
        _write_minimal_fcstd(dest)
        return {
            "success": True,
            "save_disposition": "copy_written",
            "disposition": "copy_written",
            "file_written": True,
            "unchanged": False,
            "durability_verified": True,
            "canonical_path": canonical_path,
            "target_path": dest,
            "resulting_clean": False,
            "message": "Saved copy",
        }

    document.saveCopyWithOutcome = save_copy_with_outcome
    return document


def test_save_document_copy_writes_copy_without_moving_canonical_savepoint():
    with tempfile.TemporaryDirectory() as tmp:
        canonical = os.path.join(tmp, "Model.FCStd")
        copy_path = os.path.join(tmp, "Model-copy.FCStd")
        _write_minimal_fcstd(canonical)
        document = _mock_document(canonical_path=canonical)
        result = native_lifecycle_methods._save_copy_gui(
            document,
            copy_path,
            overwrite=False,
        )

        assert result["success"] is True
        assert result["saved"] is True
        assert result["save_disposition"] == "copy_written"
        assert document.FileName == canonical
        assert os.path.isfile(copy_path)


def test_save_document_copy_refuses_existing_destination_when_overwrite_false():
    with tempfile.TemporaryDirectory() as tmp:
        canonical = os.path.join(tmp, "Model.FCStd")
        copy_path = os.path.join(tmp, "Model-copy.FCStd")
        _write_minimal_fcstd(canonical)
        _write_minimal_fcstd(copy_path)
        document = _mock_document(canonical_path=canonical)
        result = native_lifecycle_methods._save_copy_gui(
            document,
            copy_path,
            overwrite=False,
        )

    assert result["success"] is False
    assert result["error_code"] == "DESTINATION_EXISTS"


def test_save_document_copy_detects_canonical_savepoint_move():
    with tempfile.TemporaryDirectory() as tmp:
        canonical = os.path.join(tmp, "Model.FCStd")
        moved = os.path.join(tmp, "Moved.FCStd")
        copy_path = os.path.join(tmp, "Model-copy.FCStd")
        _write_minimal_fcstd(canonical)
        document = _mock_document(canonical_path=canonical)

        def save_copy_with_outcome(destination: str):
            document.FileName = moved
            dest = os.path.realpath(destination)
            _write_minimal_fcstd(dest)
            return {
                "success": True,
                "save_disposition": "copy_written",
                "file_written": True,
                "unchanged": False,
                "durability_verified": True,
                "canonical_path": moved,
                "target_path": dest,
                "resulting_clean": False,
                "message": "Saved copy",
            }

        document.saveCopyWithOutcome = save_copy_with_outcome
        result = native_lifecycle_methods._save_copy_gui(
            document,
            copy_path,
            overwrite=False,
        )

    assert result["success"] is False
    assert result["error_code"] == "CANONICAL_SAVEPOINT_MOVED"


def test_save_document_copy_is_authenticated_and_pause_gated():
    assert "save_document_copy" in dispatch_core_enforcement_auth.AUTHENTICATED_METHODS
    assert "save_document_copy" in dispatch_core._PAUSE_GATED_LIFECYCLE_METHODS


def test_save_document_copy_rpc_wraps_save_copy_with_outcome():
    source = inspect.getsource(native_lifecycle_methods.save_document_copy)
    assert "saveCopyWithOutcome" in inspect.getsource(
        native_lifecycle_methods._save_copy_gui
    )
    assert "_dispatch_gui" in source
    assert "validation_profile" in source


def test_legacy_save_as_degrades_to_verified_on_disk_save_copy():
    calls = []
    collaborators = SimpleNamespace(session_manager=None)

    def save_copy(*params):
        calls.append(params)
        return {
            "success": True,
            "saved": True,
            "file_evidence": {"archive": {"ok": True}},
            "target_path": "Model.FCStd",
        }

    facade = SimpleNamespace(
        _execution_collaborators=collaborators,
        save_document_as=lambda *_args: pytest.fail("canonical Save As must not run"),
        save_document_copy=save_copy,
    )
    selector = {"document_name": "Model"}

    result = dispatch_core.dispatch(
        facade,
        "save_document_as",
        (selector, "Model.FCStd", True, "", "default"),
    )

    assert calls == [(selector, "Model.FCStd", True, "default")]
    assert result["success"] is True
    assert result["saved"] is True
    assert result["verified"] is False
    assert result["storage_verified"] is True
    assert result["protocol_verified"] is False
    assert result["degraded"] is True
    assert result["effective_operation"] == "save_document_copy"
    assert result["canonical_savepoint_changed"] is False
    assert result["warning_code"] == "UNAUTHENTICATED_DEGRADED_SAVE_COPY"


def test_legacy_save_as_with_expected_hash_still_requires_authenticated_v2():
    provider = SimpleNamespace(
        get_request_identity=lambda: {},
        set_request_identity=lambda **_values: None,
    )
    collaborators = SimpleNamespace(
        session_manager=None,
        request_identity_provider=lambda: provider,
    )
    facade = SimpleNamespace(
        _execution_collaborators=collaborators,
        save_document_as=lambda *_args: pytest.fail("Save As must not run"),
        save_document_copy=lambda *_args: pytest.fail("Save Copy must not run"),
    )

    result = dispatch_core.dispatch(
        facade,
        "save_document_as",
        ({"document_name": "Model"}, "Model.FCStd", True, "expected-hash"),
    )

    assert result["success"] is False
    assert result["error_code"] == "LEASE_PROTOCOL_REQUIRED"
