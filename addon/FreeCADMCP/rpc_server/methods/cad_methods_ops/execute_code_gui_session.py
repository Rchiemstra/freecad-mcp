"""Session bookkeeping for GUI execute_code (Phase 4 slice 4F)."""

from __future__ import annotations

import os
from typing import Any

import FreeCAD

from ._common import require_document_modified
from .recompute_helpers import classify_recompute_errors, collect_invalid_objects


def disk_signature(doc) -> tuple | None:
    file_name = str(getattr(doc, "FileName", "") or "")
    if not file_name:
        return None
    try:
        stat = os.stat(file_name)
    except OSError:
        return (os.path.normcase(os.path.abspath(file_name)), None, None)
    return (
        os.path.normcase(os.path.abspath(file_name)),
        stat.st_mtime_ns,
        stat.st_size,
    )


def build_execute_session(
    *,
    target_doc: str | None,
    active_before: str | None,
    dirty_before: dict[str, bool],
    disk_before: dict[str, tuple | None],
    invalid_before: dict[str, list[dict[str, Any]]],
    read_only_unguarded: list[str],
    collect_invalid_objects_fn=None,
) -> dict[str, Any]:
    collector = collect_invalid_objects_fn or collect_invalid_objects
    invalid_after = collector()
    classified = classify_recompute_errors(invalid_before, invalid_after, target_doc)
    active_after = FreeCAD.ActiveDocument.Name if FreeCAD.ActiveDocument else None
    dirty_after = {
        name: require_document_modified(doc)
        for name, doc in FreeCAD.listDocuments().items()
    }
    disk_after = {
        name: disk_signature(doc) for name, doc in FreeCAD.listDocuments().items()
    }
    saved_documents = sorted(
        name
        for name, after_signature in disk_after.items()
        if after_signature is not None
        and (
            disk_before.get(name) != after_signature
            or (dirty_before.get(name) is True and dirty_after.get(name) is False)
        )
    )
    target_doc_obj = FreeCAD.getDocument(target_doc) if target_doc else None
    session = {
        "active_document_before": active_before,
        "active_document_after": active_after,
        "dirty_before": dirty_before,
        "dirty_after": dirty_after,
        "saved": bool(saved_documents),
        "saved_documents": saved_documents,
        "file_path": getattr(target_doc_obj, "FileName", "") if target_doc_obj else "",
        **classified,
    }
    if read_only_unguarded:
        session["read_only_unguarded_documents"] = read_only_unguarded
    return session
