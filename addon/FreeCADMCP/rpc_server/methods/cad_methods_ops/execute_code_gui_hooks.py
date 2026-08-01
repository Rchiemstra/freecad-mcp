"""Read-only save hooks for GUI execute_code (Phase 4 slice 4F)."""

from __future__ import annotations

import contextlib
from typing import Any

import FreeCAD


def install_read_only_save_hooks() -> tuple[list[tuple[Any, str, Any]], list[str]]:
    saved_hooks: list[tuple[Any, str, Any]] = []
    read_only_unguarded: list[str] = []

    def block_save(original):
        def wrapped(*args, **kwargs):
            raise RuntimeError("save blocked in read_only execute_code mode")

        return wrapped

    for doc_name, doc in FreeCAD.listDocuments().items():
        for attr in ("save", "saveAs", "saveCopy"):
            if not hasattr(doc, attr):
                continue
            original = getattr(doc, attr)
            try:
                setattr(doc, attr, block_save(original))
            except Exception:
                if doc_name not in read_only_unguarded:
                    read_only_unguarded.append(doc_name)
                continue
            saved_hooks.append((doc, attr, original))
    return saved_hooks, read_only_unguarded


def restore_save_hooks(saved_hooks: list[tuple[Any, str, Any]]) -> None:
    for doc, attr, original in saved_hooks:
        with contextlib.suppress(Exception):
            setattr(doc, attr, original)


def recompute_documents(
    recompute_mode: str, recompute_docs: list[str] | tuple[str, ...]
) -> None:
    if recompute_mode == "all":
        for doc in FreeCAD.listDocuments().values():
            with contextlib.suppress(Exception):
                doc.recompute()
        return
    if recompute_mode == "target" and recompute_docs:
        for doc_name in recompute_docs:
            doc = FreeCAD.getDocument(doc_name)
            if doc:
                with contextlib.suppress(Exception):
                    doc.recompute()


def restore_active_document(active_before: str | None, restore_active: bool) -> None:
    if not restore_active or not active_before:
        return
    try:
        if FreeCAD.getDocument(active_before):
            FreeCAD.setActiveDocument(active_before)
    except Exception:
        pass
