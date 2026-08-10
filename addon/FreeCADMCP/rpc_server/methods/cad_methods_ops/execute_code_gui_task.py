"""GUI-thread execute_code task (Phase 4 slice 4F)."""

from __future__ import annotations

import io
from typing import Any

from ._common import require_document_modified
from ...gui_dispatch import _flush_gui_events
from .execute_code_gui_exec import run_python_on_gui_thread
from .execute_code_gui_hooks import (
    install_read_only_save_hooks,
    recompute_documents,
    restore_active_document,
    restore_save_hooks,
)
from .execute_code_gui_session import build_execute_session, disk_signature
from .recompute_helpers import collect_invalid_objects


def run_execute_code_gui_task(
    code: str,
    options: dict[str, Any],
    *,
    freecad,
    collect_invalid_objects_fn=None,
):
    output_buffer = io.StringIO()
    target_doc = options.get("document")
    recompute_mode = options.get("recompute", "none")
    recompute_docs = options.get("recompute_documents") or (
        [target_doc] if target_doc and recompute_mode == "target" else []
    )
    read_only = bool(options.get("read_only", False))
    restore_active = bool(options.get("restore_active_document", True))
    activate_doc = bool(options.get("activate_document", False))

    active_before = freecad.ActiveDocument.Name if freecad.ActiveDocument else None
    dirty_before = {
        name: require_document_modified(doc)
        for name, doc in freecad.listDocuments().items()
    }
    disk_before = {
        name: disk_signature(doc) for name, doc in freecad.listDocuments().items()
    }
    collector = collect_invalid_objects_fn or collect_invalid_objects
    invalid_before = collector()

    if target_doc and activate_doc:
        doc = freecad.getDocument(target_doc)
        if doc:
            freecad.setActiveDocument(target_doc)

    saved_hooks: list = []
    read_only_unguarded: list[str] = []
    if read_only:
        saved_hooks, read_only_unguarded = install_read_only_save_hooks(
            freecad=freecad
        )

    ok = False
    tb_info = None
    try:
        ok, tb_info = run_python_on_gui_thread(
            code, output_buffer, freecad=freecad
        )
    finally:
        restore_save_hooks(saved_hooks)
        recompute_documents(recompute_mode, recompute_docs, freecad=freecad)
        restore_active_document(active_before, restore_active, freecad=freecad)

    if ok and not read_only:
        try:
            import FreeCADGui

            FreeCADGui.updateGui()
        except Exception:
            pass
        _flush_gui_events()

    session = build_execute_session(
        target_doc=target_doc,
        active_before=active_before,
        dirty_before=dirty_before,
        disk_before=disk_before,
        invalid_before=invalid_before,
        read_only_unguarded=read_only_unguarded,
        freecad=freecad,
        collect_invalid_objects_fn=collect_invalid_objects_fn,
    )
    stdout = output_buffer.getvalue()
    if ok:
        return {"ok": True, "session": session, "stdout": stdout}
    return {
        "ok": False,
        "error": tb_info["message"] if tb_info else "Unknown error",
        "traceback": tb_info,
        "session": session,
        "stdout": stdout,
    }
