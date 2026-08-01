"""Lease-preserving in-place snapshot restore."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

from .snapshot_restore_error import SnapshotRestoreError


def validated_snapshot_file(path: str | os.PathLike[str]) -> Path:
    target = Path(path)
    try:
        info = target.lstat()
    except OSError as exc:
        raise SnapshotRestoreError(f"snapshot file is unavailable: {exc}") from exc
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    file_attributes = int(getattr(info, "st_file_attributes", 0) or 0)
    if target.is_symlink() or file_attributes & reparse_flag:
        raise SnapshotRestoreError("snapshot file must not be a symlink or reparse point")
    if not stat.S_ISREG(info.st_mode):
        raise SnapshotRestoreError("snapshot path must be a regular file")
    if info.st_size < 22:
        raise SnapshotRestoreError("snapshot file is too small to be an FCStd archive")
    return target.resolve(strict=True)


def same_path(left: str, right: str) -> bool:
    return os.path.normcase(os.path.realpath(left)) == os.path.normcase(
        os.path.realpath(right)
    )


def force_document_dirty(document: Any) -> None:
    """Make restored in-memory state explicitly require save verification."""
    try:
        from document_state import document_modified_state, mark_document_modified
    except ImportError:
        from addon.FreeCADMCP.document_state import (
            document_modified_state,
            mark_document_modified,
        )

    if document_modified_state(document) is True:
        return
    if mark_document_modified(document):
        return
    try:
        original_comment = str(getattr(document, "Comment", ""))
        document.Comment = original_comment + "\u2060"
        document.Comment = original_comment
    except Exception as exc:
        raise SnapshotRestoreError(
            "restored document could not be marked dirty"
        ) from exc
    if document_modified_state(document) is not True:
        raise SnapshotRestoreError(
            "restored document did not report Gui::Document.Modified=true"
        )


def _validate_pre_restore(
    document: Any,
    *,
    expected_document_name: str,
    expected_source_path: str | None,
) -> tuple[str, str]:
    original_name = str(getattr(document, "Name", "") or "")
    original_path = str(getattr(document, "FileName", "") or "")
    if original_name != str(expected_document_name):
        raise SnapshotRestoreError("live document name changed before restore")
    if expected_source_path is None:
        if original_path:
            raise SnapshotRestoreError("unsaved lease unexpectedly has a file path")
    elif not original_path or not same_path(original_path, expected_source_path):
        raise SnapshotRestoreError("live document source path changed before restore")
    if bool(getattr(document, "HasPendingTransaction", False)) or bool(
        getattr(document, "Transacting", False)
    ):
        raise SnapshotRestoreError(
            "document has an active transaction and cannot be restored safely"
        )
    return original_name, original_path


def _load_snapshot_preserving_path(
    document: Any,
    target: Path,
    original_path: str,
) -> None:
    load_error: Exception | None = None
    try:
        document.load(str(target))
    except Exception as exc:
        load_error = exc
    try:
        # FileName is a transient document property.  Restoring it does not
        # write the source file; the restored state remains dirty until the
        # typed save/finalize lifecycle verifies it.
        document.FileName = original_path
    except Exception as exc:
        raise SnapshotRestoreError(
            "snapshot load changed FileName and the source path could not be restored"
        ) from exc
    if load_error is not None:
        raise SnapshotRestoreError(
            f"FreeCAD could not load the snapshot: {load_error}"
        ) from load_error


def _validate_post_restore(
    document: Any,
    *,
    original_name: str,
    original_path: str,
) -> None:
    if str(getattr(document, "Name", "") or "") != original_name:
        raise SnapshotRestoreError("snapshot restore changed the document name")
    restored_path = str(getattr(document, "FileName", "") or "")
    if original_path:
        if not restored_path or not same_path(restored_path, original_path):
            raise SnapshotRestoreError("snapshot restore changed the source path")
    elif restored_path:
        raise SnapshotRestoreError("snapshot restore changed an unsaved document path")
    if bool(getattr(document, "Partial", False)):
        raise SnapshotRestoreError("FreeCAD reported a partial snapshot restore")


def restore_snapshot_in_place_gui(
    document: Any,
    snapshot_path: str | os.PathLike[str],
    *,
    expected_document_name: str,
    expected_source_path: str | None,
    validator=None,
) -> dict[str, Any]:
    """Restore through ``Document.load`` while retaining the live proxy.

    Closing and reopening a leased document creates an unlocked identity gap.
    FreeCAD's in-place ``load`` clears/restores the same C++ Document instead.
    It temporarily points ``FileName`` at the snapshot, so the authoritative
    source path is restored before this function returns, even on failure.
    """
    target = validated_snapshot_file(snapshot_path)
    original_name, original_path = _validate_pre_restore(
        document,
        expected_document_name=expected_document_name,
        expected_source_path=expected_source_path,
    )
    _load_snapshot_preserving_path(document, target, original_path)
    _validate_post_restore(
        document,
        original_name=original_name,
        original_path=original_path,
    )

    recompute = getattr(document, "recompute", None)
    if callable(recompute):
        recompute()
    validation = validator(document) if validator is not None else {"ok": True}
    if isinstance(validation, dict) and validation.get("ok") is False:
        raise SnapshotRestoreError("snapshot post-restore validation failed")
    force_document_dirty(document)
    return {
        "ok": True,
        "document_name": original_name,
        "source_path": original_path or None,
        "dirty": True,
        "validation": validation,
    }
